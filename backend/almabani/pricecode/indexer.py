"""
Price Code Indexer - Index price codes from Excel files into Pinecone.
"""

import logging
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
import asyncio

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
        embeddings_service,
        vector_store_service,
        index_name: str = "almabani-pricecode"
    ):
        self.embeddings_service = embeddings_service
        self.vector_store_service = vector_store_service
        self.index_name = index_name
    
    def read_price_codes_from_excel(self, file_path: Path) -> List[Dict[str, Any]]:
        """
        Read price codes from Excel file.
        
        Expected columns: 'Price Code', 'Price Code Description'
        May have multiple sheets (categories like Civil, Electrical, etc.)
        """
        records = []
        source_file = file_path.stem
        
        try:
            xls = pd.ExcelFile(file_path)
            
            for sheet_name in xls.sheet_names:
                logger.info(f"Reading sheet: {sheet_name}")
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
                    
                    records.append({
                        "price_code": code,
                        "description": description,
                        "category": sheet_name,
                        "source_file": source_file
                    })
                
                logger.info(f"Extracted {len(records)} records from {sheet_name}")
        
        except Exception as e:
            logger.error(f"Error reading Excel file {file_path}: {e}")
            raise
        
        return records
    
    async def index_records(
        self,
        records: List[Dict[str, Any]],
        namespace: str = "",
        batch_size: int = 100
    ) -> int:
        """
        Embed and upsert records to Pinecone.
        
        Returns: Number of vectors indexed
        """
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
            vectors.append({
                "id": vector_id,
                "values": embedding,
                "metadata": {
                    "price_code": record["price_code"],
                    "description": record["description"],
                    "category": record["category"],
                    "source_file": record["source_file"]
                }
            })
        
        # Upsert to Pinecone
        index = self.vector_store_service.get_index(self.index_name)
        
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            await asyncio.to_thread(
                index.upsert,
                vectors=batch,
                namespace=namespace
            )
            logger.info(f"Upserted batch {i//batch_size + 1}/{(len(vectors) + batch_size - 1)//batch_size}")
        
        logger.info(f"Successfully indexed {len(vectors)} price codes")
        return len(vectors)
    
    async def index_from_excel(
        self,
        file_path: Path,
        namespace: str = ""
    ) -> int:
        """
        Read Excel file and index all price codes.
        
        Returns: Number of vectors indexed
        """
        records = self.read_price_codes_from_excel(file_path)
        return await self.index_records(records, namespace=namespace)
