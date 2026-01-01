import os
import sys
import asyncio
import logging
import json
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
from almabani.vectorstore.indexer import JSONProcessor, VectorStoreIndexer

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

def register_sheet_name(bucket, sheet_name):
    """Register a new sheet name in the available sheets registry on S3."""
    if not sheet_name:
        return
        
    s3 = boto3.client('s3')
    registry_key = "metadata/available_sheets.json"
    
    try:
        try:
            # 1. Read existing
            obj = s3.get_object(Bucket=bucket, Key=registry_key)
            data = json.loads(obj['Body'].read())
            current_sheets = set(data.get('sheets', []))
        except s3.exceptions.NoSuchKey:
            current_sheets = set()
        except Exception as e:
            logger.warning(f"Failed to read registry: {e}")
            current_sheets = set()
            
        # 2. Add new sheet (idempotent)
        if sheet_name not in current_sheets:
            logger.info(f"Registering new sheet: {sheet_name}")
            current_sheets.add(sheet_name)
            
            # 3. Write back
            new_data = {"sheets": sorted(list(current_sheets))}
            s3.put_object(
                Bucket=bucket, 
                Key=registry_key, 
                Body=json.dumps(new_data),
                ContentType='application/json'
            )
    except Exception as e:
        logger.error(f"Failed to register sheet name: {e}")

async def process_parse(input_path: Path, storage):
    logger.info(f"Starting PARSE job for {input_path}")
    
    settings, _openai_async, embeddings_service, vector_store_service = get_services()
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
    
    # Also push parsed sheets into the vector index (sequential to avoid memory spikes)
    processor = JSONProcessor()
    indexer = VectorStoreIndexer(embeddings_service, vector_store_service)
    namespace = settings.pinecone_namespace or ""
    
    for f in output_files:
        try:
            doc = processor.process_file(f)
        except Exception as e:
            logger.error(f"Failed to process JSON for indexing {f}: {e}", exc_info=True)
            continue
        
        try:
            await indexer.index_documents(
                [doc],
                embedding_batch_size=settings.batch_size,
                upsert_batch_size=settings.pinecone_batch_size,
                namespace=namespace,
                max_workers=settings.max_workers
            )
            logger.info(f"Indexed '{doc.source_name}' ({doc.total_items} items) into vector store")
            
            # Register the sheet name
            bucket_name = os.getenv('S3_BUCKET_NAME')
            if bucket_name:
                register_sheet_name(bucket_name, doc.source_name)
                
        except Exception as e:
            logger.error(f"Failed to index document {f}: {e}", exc_info=True)
            continue

async def process_fill(input_path: Path, storage):
    logger.info(f"Starting FILL job for {input_path}")
    
    settings, openai_async, embeddings_service, vector_store_service = get_services()
    
    # Read S3 metadata to get sheet selection
    s3_key = os.getenv('S3_KEY')
    bucket_name = os.getenv('S3_BUCKET_NAME')
    filter_dict = None
    
    if s3_key and bucket_name:
        try:
            s3 = boto3.client('s3')
            head = s3.head_object(Bucket=bucket_name, Key=s3_key)
            metadata = head.get('Metadata', {})
            sheet_names_str = metadata.get('sheet-names', '')
            
            logger.info(f"DEBUG: S3 metadata sheet-names: '{sheet_names_str}'")
            
            if sheet_names_str:
                selected_sheets = [s.strip() for s in sheet_names_str.split(',') if s.strip()]
                logger.info(f"DEBUG: Parsed sheets from S3 metadata: {selected_sheets}")
                if selected_sheets:
                    filter_dict = {'sheet_name': {'$in': selected_sheets}}
                    logger.info(f"DEBUG: Created Pinecone filter: {filter_dict}")
        except Exception as e:
            logger.warning(f"Failed to read S3 metadata: {e}. Will search all sheets.")
    else:
        logger.info("DEBUG: No S3_KEY or S3_BUCKET_NAME, will search ALL sheets (no filter)")
    
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
        workers=settings.max_workers,
        filter_dict=filter_dict
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
    
    # DEBUG: Log all environment variables
    selected_sheet_names_env = os.environ.get('SELECTED_SHEET_NAMES', '')
    logger.info(f"DEBUG: Environment variables:")
    logger.info(f"  - JOB_MODE: {mode}")
    logger.info(f"  - S3_KEY: {s3_key}")
    logger.info(f"  - SELECTED_SHEET_NAMES: '{selected_sheet_names_env}'")
    
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
