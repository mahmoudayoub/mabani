"""
Price Code Worker - Fargate worker for price code indexing and allocation.

Modes:
- INDEX: Index price codes from Excel files into Pinecone
- ALLOCATE: Allocate price codes to BOQ items
"""

import os
import sys
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote_plus
import boto3

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from almabani.config.settings import Settings, get_settings
from almabani.core.storage import StorageService, get_storage
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.pricecode.indexer import PriceCodeIndexer
from almabani.pricecode.matcher import PriceCodeMatcher
from almabani.pricecode.pipeline import PriceCodePipeline
from openai import AsyncOpenAI

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pricecode_worker")


def get_services():
    """Initialize all required services"""
    from almabani.config.settings import get_pinecone_client
    settings = get_settings()
    
    openai_async = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries
    )
    
    pinecone_client = get_pinecone_client()
    
    embeddings_service = EmbeddingsService(
        async_client=openai_async,
        model=settings.openai_embedding_model,
        max_workers=settings.max_workers
    )
    
    # Use price code index instead of main index
    pricecode_index = os.getenv('PRICECODE_INDEX_NAME', 'almabani-pricecode')
    vector_store_service = VectorStoreService(
        client=pinecone_client,
        index_name=pricecode_index,
        environment=settings.pinecone_environment
    )
    
    return settings, openai_async, embeddings_service, vector_store_service


async def process_index(input_path: Path, storage):
    """
    Index price codes from Excel file into Pinecone.
    """
    logger.info(f"Starting INDEX job for {input_path}")
    
    settings, _, embeddings_service, vector_store_service = get_services()
    
    indexer = PriceCodeIndexer(
        embeddings_service=embeddings_service,
        vector_store_service=vector_store_service
    )
    
    # Index the file
    count = await indexer.index_from_excel(input_path, namespace="")
    
    # Upload result to S3
    result = {
        "source_file": input_path.name,
        "indexed_count": count,
        "completed_at": datetime.now().isoformat(),
        "index_name": pricecode_index
    }
    
    result_key = f"output/pricecode/index/{input_path.stem}_indexed.json"
    storage.upload_json(result, result_key)
    logger.info(f"Indexing complete: {count} price codes indexed")
    logger.info(f"Result uploaded to {result_key}")
    
    # Update metadata registry
    bucket_name = os.getenv('S3_BUCKET_NAME')
    if bucket_name:
        try:
            s3 = boto3.client('s3')
            
            # Read existing registry
            try:
                obj = s3.get_object(Bucket=bucket_name, Key="metadata/available_price_codes.json")
                registry = json.loads(obj['Body'].read().decode('utf-8'))
            except:
                registry = {"price_codes": []}
            
            # Add new code set name
            code_name = input_path.stem
            if code_name not in registry["price_codes"]:
                registry["price_codes"].append(code_name)
                s3.put_object(
                    Bucket=bucket_name,
                    Key="metadata/available_price_codes.json",
                    Body=json.dumps(registry, indent=2),
                    ContentType="application/json"
                )
                logger.info(f"Updated metadata registry with: {code_name}")
            else:
                logger.info(f"Code set {code_name} already in registry")
        except Exception as e:
            logger.warning(f"Failed to update metadata registry: {e}")


async def process_allocate(input_path: Path, storage):
    """
    Allocate price codes to BOQ items in Excel file.
    """
    logger.info(f"Starting ALLOCATE job for {input_path}")
    
    settings, openai_async, embeddings_service, vector_store_service = get_services()
    bucket_name = os.getenv('S3_BUCKET_NAME')
    
    # Create estimate file
    estimate_key = None
    try:
        # Count items (read file to count)
        import pandas as pd
        xls = pd.ExcelFile(input_path)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        total_items = len(df)
        
        # Estimate: ~1 second per item with concurrency
        SECONDS_PER_BATCH = 10
        CONCURRENT = 20
        batches = (total_items + CONCURRENT - 1) // CONCURRENT
        estimated_seconds = max(30, batches * SECONDS_PER_BATCH + 10)
        
        # Get task ARN
        task_arn = None
        cluster_name = os.getenv('ECS_CLUSTER_NAME', '')
        try:
            from urllib.request import urlopen
            metadata_uri = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
            if metadata_uri:
                with urlopen(f"{metadata_uri}/task") as response:
                    task_metadata = json.loads(response.read().decode())
                    task_arn = task_metadata.get('TaskARN', '')
        except Exception as e:
            logger.warning(f"Failed to get task ARN: {e}")
        
        estimate_data = {
            "total_items": total_items,
            "estimated_seconds": estimated_seconds,
            "started_at": datetime.now().isoformat(),
            "filename": input_path.stem,
            "task_arn": task_arn,
            "cluster_name": cluster_name
        }
        
        estimate_key = f"estimates/pc_{input_path.stem}_estimate.json"
        storage.upload_json(estimate_data, estimate_key)
        logger.info(f"Uploaded estimate to {estimate_key}")
        
    except Exception as e:
        logger.warning(f"Failed to create estimate: {e}")
    
    # Create matcher and pipeline
    matcher = PriceCodeMatcher(
        async_openai_client=openai_async,
        embeddings_service=embeddings_service,
        vector_store_service=vector_store_service,
        top_k=20,
        model=settings.openai_chat_model
    )
    
    pipeline = PriceCodePipeline(matcher)
    
    # Process file
    try:
        output_filename = f"{input_path.stem}_pricecode.xlsx"
        output_path = input_path.parent / output_filename
        
        result = await pipeline.process_file(
            input_file=input_path,
            output_file=output_path,
            namespace="",
            max_concurrent=20
        )
        
        # Upload result
        s3_key = f"output/pricecode/{output_filename}"
        storage.upload_file(output_path, s3_key)
        logger.info(f"Uploaded result: {s3_key}")
        
        # Update estimate with success
        if estimate_key and bucket_name:
            try:
                s3 = boto3.client('s3')
                estimate_obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(estimate_obj['Body'].read().decode('utf-8'))
                estimate['complete'] = True
                estimate['success'] = True
                estimate['result'] = result
                s3.put_object(
                    Bucket=bucket_name,
                    Key=estimate_key,
                    Body=json.dumps(estimate),
                    ContentType='application/json'
                )
                logger.info(f"Updated estimate with success")
            except Exception as e:
                logger.warning(f"Failed to update estimate: {e}")
        
        logger.info(f"Allocation complete: {result['matched']}/{result['total_items']} matched")
        
    except Exception as e:
        # Update estimate with failure
        if estimate_key and bucket_name:
            try:
                s3 = boto3.client('s3')
                estimate_obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(estimate_obj['Body'].read().decode('utf-8'))
                estimate['complete'] = True
                estimate['success'] = False
                estimate['error'] = str(e)
                s3.put_object(
                    Bucket=bucket_name,
                    Key=estimate_key,
                    Body=json.dumps(estimate),
                    ContentType='application/json'
                )
            except Exception as ue:
                logger.error(f"Failed to update estimate with error: {ue}")
        
        logger.error(f"Processing failed: {e}")
        raise


async def main():
    """Main entry point"""
    mode = os.getenv('JOB_MODE', '').upper()
    s3_key = os.getenv('S3_KEY')
    
    logger.info(f"Price Code Worker started. Mode: {mode}, Key: {s3_key}")
    
    if not s3_key:
        logger.error("No S3_KEY provided. Exiting.")
        sys.exit(1)
    
    storage = get_storage()
    
    # Download input file
    local_filename = Path(s3_key).name
    local_input = Path(f"/tmp/{local_filename}")
    local_input.parent.mkdir(exist_ok=True, parents=True)
    
    logger.info(f"Downloading {s3_key}...")
    try:
        storage.download_file(s3_key, local_input)
    except Exception as e:
        logger.error(f"Failed to download: {e}")
        sys.exit(1)
    
    try:
        if mode == 'INDEX':
            await process_index(local_input, storage)
        elif mode == 'ALLOCATE':
            await process_allocate(local_input, storage)
        else:
            # Auto-detect from path
            if '/index/' in s3_key:
                await process_index(local_input, storage)
            elif '/allocate/' in s3_key:
                await process_allocate(local_input, storage)
            else:
                logger.error(f"Unknown mode and cannot detect from path: {s3_key}")
                sys.exit(1)
    
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        sys.exit(1)
    
    logger.info("Job complete successfully.")


if __name__ == "__main__":
    asyncio.run(main())
