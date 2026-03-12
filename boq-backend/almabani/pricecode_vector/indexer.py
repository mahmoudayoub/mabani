"""
Price Code Vector Indexer – parse a filled BOQ and store items in S3 Vectors.

Reads an Excel BOQ that already has price codes filled.  For every leaf item
with a non-empty price code it:
  1. Builds an embedding text from description + hierarchy + unit.
  2. Stores the vector in S3 Vectors with rich metadata for filtering.

Metadata stored per vector
--------------------------
  source_file : str   – stem of the uploaded Excel (for filtering / deletion)
  sheet_name  : str   – worksheet name
  price_code  : str   – the assigned price code
  description : str   – item description text
  parent      : str   – parent category
  grandparent : str   – grandparent category
  unit        : str   – unit of measure
  category_path : str – full hierarchy breadcrumb
  item_code   : str   – item number / code column
  row_index   : int   – original 0-based row index
"""

import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pandas as pd

from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.parsers.excel_parser import ExcelParser
from almabani.parsers.hierarchy_processor import HierarchyProcessor
from almabani.core.models import ItemType

logger = logging.getLogger(__name__)

# S3 Vectors index name for this service
PRICECODE_VECTOR_INDEX = "almabani-pricecode-vector"


class PriceCodeVectorIndexer:
    """Parse a filled BOQ and index items into S3 Vectors."""

    def __init__(
        self,
        embeddings_service: EmbeddingsService,
        vector_store: VectorStoreService,
    ):
        self.embeddings = embeddings_service
        self.vector_store = vector_store
        self.excel_parser = ExcelParser()
        self.hierarchy_processor = HierarchyProcessor()

    # ── public API ──────────────────────────────────────────────────────

    async def index_file(
        self,
        file_path: Path,
        source_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Parse *file_path* (a filled BOQ) and upsert its items into
        the vector store.

        Returns a summary dict with counts.
        """
        source_name = source_name or file_path.stem

        logger.info(f"Indexing filled BOQ: {file_path.name} (source={source_name})")

        sheets_data = await asyncio.to_thread(
            self.excel_parser.excel_io.read_excel, str(file_path)
        )

        total_indexed = 0
        sheet_reports: List[Dict[str, Any]] = []

        for sheet_name, (df, header_row_idx) in sheets_data.items():
            columns = self.excel_parser.excel_io.detect_columns(df)
            logger.info(f"Sheet '{sheet_name}' columns: {columns}")

            parent_map = self._build_parent_map(df, header_row_idx, columns)
            items = self._extract_filled_items(
                df, header_row_idx, columns, parent_map, source_name, sheet_name
            )

            if not items:
                logger.info(f"Sheet '{sheet_name}': no filled items found, skipping")
                continue

            logger.info(f"Sheet '{sheet_name}': {len(items)} filled items to index")

            # Build embedding texts
            texts = [self._build_embedding_text(item) for item in items]

            # Generate embeddings in batch
            embeddings = await self.embeddings.generate_embeddings_batch(texts)

            # Prepare vector dicts for upload
            vectors = []
            for item, embedding in zip(items, embeddings):
                vec_id = f"{source_name}__{sheet_name}__{item['row_index']}"
                vec_id = VectorStoreService.sanitize_id(vec_id)
                metadata = {
                    "source_file": source_name,
                    "sheet_name": sheet_name,
                    "price_code": item["price_code"],
                    "description": item["description"],
                    "parent": item.get("parent") or "",
                    "grandparent": item.get("grandparent") or "",
                    "unit": item.get("unit") or "",
                    "category_path": item.get("category_path") or "",
                    "item_code": item.get("item_code") or "",
                    "row_index": item["row_index"],
                }
                vectors.append({
                    "id": vec_id,
                    "embedding": embedding,
                    "text": texts[items.index(item)],
                    "metadata": metadata,
                })

            # Upload to S3 Vectors
            result = await self.vector_store.upload_vectors(vectors, batch_size=50)
            count = result.get("uploaded_count", 0)
            total_indexed += count
            sheet_reports.append({
                "sheet_name": sheet_name,
                "items_found": len(items),
                "indexed": count,
            })
            logger.info(f"Sheet '{sheet_name}': indexed {count} vectors")

        return {
            "source_file": source_name,
            "total_indexed": total_indexed,
            "sheets": sheet_reports,
        }

    # ── parsing helpers (reuse pricecode pipeline logic) ────────────────

    def _build_parent_map(
        self,
        df: pd.DataFrame,
        header_row_idx: int,
        columns: Dict[str, str],
    ) -> Dict[int, Dict[str, Optional[str]]]:
        """Build row → {parent, grandparent, category_path} map."""
        raw_items = self.excel_parser._extract_raw_items(df, columns, header_row_idx)
        tree = self.hierarchy_processor._build_hierarchy(raw_items)

        parent_map: Dict[int, Dict[str, Optional[str]]] = {}

        def walk(nodes, parent_desc, grandparent_desc, path):
            for node in nodes:
                node_parent = parent_desc
                node_grandparent = grandparent_desc
                path_added = False

                if node.item_type in (ItemType.NUMERIC_LEVEL, ItemType.SUBCATEGORY):
                    node_grandparent = parent_desc
                    node_parent = node.description
                    if node.description:
                        path.append(str(node.description))
                        path_added = True

                if node.item_type == ItemType.ITEM and node.row_number is not None:
                    parent_map[node.row_number] = {
                        "parent": node_parent,
                        "grandparent": node_grandparent,
                        "category_path": " > ".join(path) if path else None,
                    }

                if node.children:
                    walk(node.children, node_parent, node_grandparent, path)

                if path_added:
                    path.pop()

        walk(tree, None, None, [])
        return parent_map

    def _extract_filled_items(
        self,
        df: pd.DataFrame,
        header_row_idx: int,
        columns: Dict[str, str],
        parent_map: Dict[int, Dict[str, Optional[str]]],
        source_name: str,
        sheet_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Extract leaf items that **already have** a price code filled.

        This is the inverse of ``_extract_items_for_allocation`` in the
        lexical pipeline: here we *require* a non-empty code column.
        """
        items: List[Dict[str, Any]] = []

        level_col = columns.get("level")
        item_col = columns.get("item")
        desc_col = columns.get("description")
        unit_col = columns.get("unit")
        code_col = self._detect_code_column(df, header_row_idx, columns)

        if not code_col:
            logger.warning(
                f"No price-code column detected in sheet '{sheet_name}' – skipping"
            )
            return items

        for idx in range(header_row_idx + 1, len(df)):
            row = df.iloc[idx]

            level_val = row.get(level_col) if level_col else None
            item_val = row.get(item_col) if item_col else None
            desc_val = row.get(desc_col) if desc_col else None
            unit_val = row.get(unit_col) if unit_col else None
            code_val = row.get(code_col) if code_col else None

            # Clean NaN
            level_val = None if pd.isna(level_val) else level_val
            item_val = None if pd.isna(item_val) else item_val
            desc_val = None if pd.isna(desc_val) else desc_val
            unit_val = None if pd.isna(unit_val) else unit_val
            code_val = None if pd.isna(code_val) else code_val

            has_level = level_val is not None and str(level_val).strip() != ""
            has_desc = desc_val is not None and str(desc_val).strip() != ""
            has_code = (
                code_val is not None
                and str(code_val).strip() not in ("", "nan", "None")
            )

            # Only index leaf items with an existing price code
            if not has_level and has_desc and has_code:
                map_key = idx + 1  # parent_map uses 1-based row_number
                parent = parent_map.get(map_key, {}).get("parent")
                grandparent = parent_map.get(map_key, {}).get("grandparent")
                category_path = parent_map.get(map_key, {}).get("category_path")

                items.append({
                    "row_index": idx,
                    "item_code": str(item_val).strip() if item_val else "",
                    "description": str(desc_val).strip(),
                    "unit": str(unit_val).strip() if unit_val else "",
                    "price_code": str(code_val).strip(),
                    "parent": parent,
                    "grandparent": grandparent,
                    "category_path": category_path,
                })

        return items

    def _detect_code_column(
        self,
        df: pd.DataFrame,
        header_row_idx: int,
        columns: Dict[str, str],
    ) -> Optional[str]:
        """
        Detect the Price Code column using the same 3-tier strategy
        as ``PriceCodePipeline.process_file``.
        """
        # 1. Explicit "Price Code"
        for col in df.columns:
            if "price code" in str(col).lower():
                return col

        # 2. "Code" under a "Pricing" group header
        if header_row_idx > 0:
            group_row = df.iloc[header_row_idx - 1]
            code_candidates = []
            for col_idx, col in enumerate(df.columns):
                col_lower = str(col).lower()
                if (
                    "code" in col_lower
                    and "description" not in col_lower
                    and "item" not in col_lower
                ):
                    item_col = columns.get("item")
                    if item_col and item_col == col:
                        continue
                    code_candidates.append((col_idx, col))

            for col_idx, col in code_candidates:
                gv = group_row.iloc[col_idx] if col_idx < len(group_row) else None
                if gv is not None and not pd.isna(gv):
                    gs = str(gv).strip().lower()
                    if "pricing" in gs or "price" in gs:
                        return col
                # Scan leftward
                for scan in range(col_idx - 1, max(col_idx - 6, -1), -1):
                    if 0 <= scan < len(group_row):
                        sv = group_row.iloc[scan]
                        if sv is not None and not pd.isna(sv):
                            ss = str(sv).strip().lower()
                            if "pricing" in ss or "price" in ss:
                                return col
                            break

        # 3. Fallback generic "Code"
        for col in df.columns:
            col_lower = str(col).lower()
            if (
                "code" in col_lower
                and "description" not in col_lower
                and "item" not in col_lower
            ):
                item_col = columns.get("item")
                if item_col and item_col == col:
                    continue
                return col

        return None

    @staticmethod
    def _build_embedding_text(item: Dict[str, Any]) -> str:
        """
        Compose the text that will be embedded.

        Format: ``[category_path] description (Unit: unit)``
        """
        parts: List[str] = []
        if item.get("category_path"):
            parts.append(f"[{item['category_path']}]")
        if item.get("description"):
            parts.append(item["description"])
        if item.get("unit"):
            parts.append(f"(Unit: {item['unit']})")
        return " ".join(parts)
