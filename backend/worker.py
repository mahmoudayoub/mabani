import os
import sys
import asyncio
import logging
from pathlib import Path
from urllib.parse import unquote_plus
import boto3

# Add current dir to path to key imports working
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from almabani.core.storage import get_storage
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.rate_matcher.matcher import RateMatcher
from almabani.config.settings import get_settings, get_openai_client, get_pinecone_client
from almabani.core.embeddings import EmbeddingsService
from almabani.core.vector_store import VectorStoreService
from almabani.rate_matcher.pipeline import RateFillerPipeline

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

def get_services():
    settings = get_settings()
    from openai import AsyncOpenAI
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
    
    vector_store_service = VectorStoreService(
        client=pinecone_client,
        index_name=settings.pinecone_index_name,
        environment=settings.pinecone_environment
    )
    
    return settings, openai_async, embeddings_service, vector_store_service

async def process_parse(input_path: Path, storage):
    logger.info(f"Starting PARSE job for {input_path}")
    
    output_dir = input_path.parent / "output"
    output_dir.mkdir(exist_ok=True, parents=True)
    
    pipeline = ExcelToJsonPipeline()
    output_files = pipeline.process_file(
        input_file=input_path,
        output_mode="multiple",
        output_dir=output_dir
    )
    
    timestamp = input_path.stem.split('_')[0] 
    
    for f in output_files:
        s3_key = f"output/indexes/{f.name}"
        storage.upload_file(f, s3_key)
        logger.info(f"Uploaded result: {s3_key}")

async def process_fill(input_path: Path, storage):
    logger.info(f"Starting FILL job for {input_path}")
    
    settings, openai_async, embeddings_service, vector_store_service = get_services()
    
    rate_matcher = RateMatcher(
        async_openai_client=openai_async,
        embeddings_service=embeddings_service,
        vector_store_service=vector_store_service,
        similarity_threshold=settings.similarity_threshold,
        top_k=settings.top_k,
        model=settings.openai_chat_model,
        verbose_logging=True
    )
    
    pipeline = RateFillerPipeline(rate_matcher)
    
    output_filename = f"{input_path.stem}_filled.xlsx"
    output_path = input_path.parent / output_filename
    
    result = await pipeline.process_file(
        input_file=input_path,
        output_file=output_path,
        namespace=settings.pinecone_namespace or "",
        workers=settings.max_workers
    )
    
    s3_key = f"output/fills/{output_filename}"
    storage.upload_file(output_path, s3_key)
    logger.info(f"Uploaded result: {s3_key}")
    
    # Summary
    summary_local = result.get('summary_file')
    if summary_local:
         summary_path = Path(summary_local)
         storage.upload_file(summary_path, f"output/fills/{summary_path.name}")


async def main():
    # Environment variables passed by the Lambda trigger/ECS definition
    # MODE: 'PARSE' or 'FILL'
    # S3_KEY: The key of the input file
    
    mode = os.getenv('JOB_MODE', '').upper()
    s3_key = os.getenv('S3_KEY')
    
    if not s3_key:
        logger.error("No S3_KEY provided. Exiting.")
        sys.exit(1)
        
    logger.info(f"Worker started. Mode: {mode}, Key: {s3_key}")
    
    storage = get_storage()
    
    # Download input
    local_filename = Path(s3_key).name
    local_input = Path(f"/tmp/{local_filename}")
    local_input.parent.mkdir(exist_ok=True, parents=True)
    
    logger.info(f"Downloading {s3_key} to {local_input}...")
    try:
        storage.download_file(s3_key, local_input)
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        sys.exit(1)
        
    try:
        if mode == 'PARSE':
            await process_parse(local_input, storage)
        elif mode == 'FILL':
            await process_fill(local_input, storage)
        else:
            # Auto-detect based on folder?
            # e.g. input/parse/file.xlsx
            if '/parse/' in s3_key:
                await process_parse(local_input, storage)
            elif '/fill/' in s3_key:
                await process_fill(local_input, storage)
            else:
                logger.error("Unknown mode and cannot detect from path.")
                sys.exit(1)
                
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        sys.exit(1)
        
    logger.info("Job complete successfully.")

if __name__ == "__main__":
    asyncio.run(main())
