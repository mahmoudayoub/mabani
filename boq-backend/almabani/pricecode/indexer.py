"""
Price Code Indexer – Build a SQLite lexical index from reference Excel files.

Replaces the old embedding-based indexer with a local lexical index.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional

from .lexical_search import build_index

logger = logging.getLogger(__name__)


class PriceCodeIndexer:
    """
    Index price codes from Excel reference files into a SQLite lexical index.

    Each reference row is tokenized, spec-extracted, and stored in an inverted
    index for fast retrieval by ``LexicalMatcher``.
    """

    def __init__(self) -> None:
        pass  # no external service dependencies

    def index_from_excel(
        self,
        file_paths: List[Path],
        db_path: str,
        rebuild: bool = False,
    ) -> int:
        """
        Read one or more reference Excel files and build a SQLite index.

        Args:
            file_paths: List of reference Excel workbook paths.
            db_path:    Output SQLite database path.
            rebuild:    Force rebuild even if the index looks up-to-date.

        Returns:
            Number of reference rows indexed.
        """
        ref_paths = [str(p) for p in file_paths]
        logger.info(f"Building lexical index from {len(ref_paths)} reference file(s) → {db_path}")

        build_index(db_path, ref_paths, rebuild=rebuild)

        # Read back the count
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute("SELECT value FROM meta WHERE key = 'ref_count'").fetchone()
            count = int(row[0]) if row else 0
        finally:
            conn.close()

        logger.info(f"Indexed {count:,} reference rows into {db_path}")
        return count

    def vacuum(self, db_path: str) -> None:
        """VACUUM the database to minimise file size before upload."""
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("VACUUM")
        finally:
            conn.close()
        logger.info(f"VACUUMed {db_path}")
