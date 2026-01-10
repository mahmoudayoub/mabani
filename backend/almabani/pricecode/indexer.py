"""
Price Code Indexer - Index price codes from Excel files into Pinecone.

Uses native async Pinecone operations.
"""

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
import os

from almabani.core.async_vector_store import get_async_vector_store

logger = logging.getLogger(__name__)


class PriceCodeIndexer:
    """
    Index price codes from Excel files into Pinecone vector store.
    
    Each vector represents a price code with:
    - Embedding of the description
    - Metadata: price_code, description, category, source_file
    """
    
    def __init__(
        self,
        embeddings_service
    ):
        self.embeddings_service = embeddings_service
    
    def yield_records_from_excel(self, file_path: Path, batch_size: int = 1000):
        """
        Yield price codes from Excel file in batches.
        
        Expected columns: 'Price Code', 'Price Code Description'
        May have multiple sheets (categories like Civil, Electrical, etc.)
        """
        source_file = file_path.stem
        records_batch = []
        
        try:
            xls = pd.ExcelFile(file_path)
            
            for sheet_name in xls.sheet_names:
                logger.info(f"Reading sheet: {sheet_name}")
                # Use stream-like reading if possible, but pandas reads whole sheet.
                # Since sheets usually < memory limit, we focus on not accumulating ALL sheets.
                df = pd.read_excel(xls, sheet_name=sheet_name)
                
                # Find the price code and description columns
                code_col = None
                desc_col = None
                
                for col in df.columns:
                    col_lower = str(col).lower()
                    if 'price code' in col_lower and 'description' not in col_lower:
                        code_col = col
                    elif 'description' in col_lower:
                        desc_col = col
                
                if not code_col or not desc_col:
                    logger.warning(f"Sheet {sheet_name} missing required columns. Found: {df.columns.tolist()}")
                    continue
                
                # Extract records
                for idx, row in df.iterrows():
                    code = str(row[code_col]).strip() if pd.notna(row[code_col]) else ""
                    description = str(row[desc_col]).strip() if pd.notna(row[desc_col]) else ""
                    
                    # Skip empty rows
                    if not code or not description or code == 'nan':
                        continue
                    
                    records_batch.append({
                        "price_code": code,
                        "description": description,
                        "category": sheet_name,  # Keep legacy field
                        "source_file": source_file,
                        # New reference fields
                        "reference_sheet": sheet_name,
                        "reference_category": sheet_name,
                        "reference_row": idx + 2
                    })
                    
                    # Yield batch if full
                    if len(records_batch) >= batch_size:
                        yield records_batch
                        records_batch = []
                
            # Yield remaining
            if records_batch:
                yield records_batch
        
        except Exception as e:
            logger.error(f"Error reading Excel file {file_path}: {e}")
            raise
    
    async def index_records(
        self,
        records: List[Dict[str, Any]],
        namespace: str = "",
        batch_size: int = None
    ) -> int:
        """
        Embed and upsert records to Pinecone using native async.
        
        Returns: Number of vectors indexed
        """
        # Load batch_size from settings if not provided
        if batch_size is None:
            from almabani.config.settings import get_settings
            batch_size = get_settings().pricecode_batch_size
        if not records:
            logger.warning("No records to index")
            return 0
        
        logger.info(f"Indexing {len(records)} price code records...")
        
        # Prepare texts for embedding (use description as the searchable text)
        texts = [r["description"] for r in records]
        
        # Generate embeddings in batches
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            embeddings = await self.embeddings_service.generate_embeddings_batch(batch_texts)
            all_embeddings.extend(embeddings)
            logger.info(f"Embedded batch {i//batch_size + 1}/{(len(texts) + batch_size - 1)//batch_size}")
        
        # Prepare vectors for upsert
        vectors = []
        for idx, (record, embedding) in enumerate(zip(records, all_embeddings)):
            vector_id = f"pc_{record['source_file']}_{record['category']}_{idx}"
            # Sanitize ID for Pinecone
            vector_id = vector_id.replace(' ', '_').replace('/', '_')[:512]
            
            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "price_code": record["price_code"],
                    "description": record["description"],
                    "category": record["category"],
                    "source_file": record["source_file"],
                    "reference_sheet": record.get("reference_sheet", ""),
                    "reference_category": record.get("reference_category", ""),
                    "reference_row": record.get("reference_row", 0)
                }
            })
        
        # Upsert to Pinecone using native async
        async with get_async_vector_store() as vector_store:
            count = await vector_store.upsert(
                vectors=vectors,
                namespace=namespace,
                batch_size=batch_size
            )
        
        logger.info(f"Successfully indexed {count} price codes")
        return count
    
    async def index_from_excel(
        self,
        file_path: Path,
        namespace: str = ""
    ) -> int:
        """
        Read Excel file and index all price codes using streaming to save memory.
        
        Returns: Number of vectors indexed
        """
        from almabani.config.settings import get_settings
        batch_size = get_settings().pricecode_batch_size or 100
        
        total_count = 0
        # Use a slightly larger read batch for efficiency vs embedding batch
        read_batch_size = batch_size * 5 
        
        logger.info(f"Starting streaming index of {file_path}")
        
        for batch in self.yield_records_from_excel(file_path, batch_size=read_batch_size):
            count = await self.index_records(batch, namespace=namespace, batch_size=batch_size)
            total_count += count
            logger.info(f"Progress: {total_count} records indexed so far")
            
        return total_count
