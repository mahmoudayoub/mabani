import os
import sys
import asyncio
import logging
import json
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote_plus
import boto3

# Add current dir to path to key imports working
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from almabani.core.storage import get_storage
from almabani.parsers.pipeline import ExcelToJsonPipeline
from almabani.rate_matcher.matcher import RateMatcher
from almabani.config.settings import get_settings, get_openai_client, get_vector_store
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
    
    vector_store_service = get_vector_store()
    
    embeddings_service = EmbeddingsService(
        async_client=openai_async,
        model=settings.openai_embedding_model,
        max_workers=settings.max_workers
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
            # 1. Read existing (includes sheets AND groups)
            obj = s3.get_object(Bucket=bucket, Key=registry_key)
            data = json.loads(obj['Body'].read())
            current_sheets = set(data.get('sheets', []))
            existing_groups = data.get('groups', [])  # Preserve groups!
        except s3.exceptions.NoSuchKey:
            current_sheets = set()
            existing_groups = []
        except Exception as e:
            logger.warning(f"Failed to read registry: {e}")
            current_sheets = set()
            existing_groups = []
            
        # 2. Add new sheet (idempotent)
        if sheet_name not in current_sheets:
            logger.info(f"Registering new sheet: {sheet_name}")
            current_sheets.add(sheet_name)
            
            # 3. Write back (preserve groups!)
            new_data = {
                "sheets": sorted(list(current_sheets)),
                "groups": existing_groups  # Keep existing groups intact
            }
            s3.put_object(
                Bucket=bucket, 
                Key=registry_key, 
                Body=json.dumps(new_data, indent=2),
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
    namespace = ""
    
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
                upsert_batch_size=settings.batch_size,
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
    
    # Read S3 metadata to get sheet selection (required - fail fast if invalid/missing)
    s3_key = os.getenv('S3_KEY')
    bucket_name = os.getenv('S3_BUCKET_NAME')
    if not s3_key or not bucket_name:
        raise RuntimeError(
            "Missing required S3 context for sheet filtering. "
            f"S3_KEY set={bool(s3_key)}, S3_BUCKET_NAME set={bool(bucket_name)}"
        )

    s3 = boto3.client('s3')
    try:
        head = s3.head_object(Bucket=bucket_name, Key=s3_key)
    except Exception as e:
        raise RuntimeError(
            f"Failed to read S3 object metadata for filter extraction: s3://{bucket_name}/{s3_key}"
        ) from e

    metadata = head.get('Metadata', {}) or {}
    sheet_names_str = str(metadata.get('sheet-names', '')).strip()

    logger.info(f"DEBUG: S3 metadata sheet-names: '{sheet_names_str}'")

    if not sheet_names_str:
        raise RuntimeError(
            "Required S3 metadata 'sheet-names' is missing or empty. "
            "Refusing unfiltered unit-rate search."
        )

    selected_sheets = [s.strip() for s in sheet_names_str.split(',') if s.strip()]
    if not selected_sheets:
        raise RuntimeError(
            "S3 metadata 'sheet-names' was provided but produced no valid sheet names. "
            "Refusing unfiltered unit-rate search."
        )

    logger.info(f"DEBUG: Parsed sheets from S3 metadata: {selected_sheets}")
    filter_dict = {'sheet_name': {'$in': selected_sheets}}
    logger.info(f"DEBUG: Created vector filter: {filter_dict}")
    
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
    
    # Count items to fill and calculate estimate
    logger.info("📊 Counting items to fill...")
    estimate_key = None  # Track estimate key for cleanup
    
    try:
        # Read Excel to count items
        sheets_data = await asyncio.to_thread(
            pipeline.excel_io.read_excel, 
            str(input_path)
        )
        selected_sheet = next(iter(sheets_data.keys()))
        df, header_row_idx = sheets_data[selected_sheet]
        columns = pipeline.excel_io.detect_columns(df)
        parent_map = await asyncio.to_thread(
            pipeline._build_parent_map, df, header_row_idx, columns
        )
        items_to_fill = await asyncio.to_thread(
            pipeline._extract_items_for_filling,
            df, header_row_idx, columns, parent_map
        )
        
        total_items = len(items_to_fill)
        logger.info(f"📊 Total items to fill: {total_items}")
        
        # Calculate estimate accounting for async parallel processing
        # Calibrated from actual performance data (59K items, 594 min total)
        # Formula: cold_start + (batches * seconds_per_batch) + overhead
        COLD_START_SECONDS = 15        # ECS/Fargate cold start time
        SECONDS_PER_BATCH = 35         # Time to process one batch of 200 items in parallel
        BASE_OVERHEAD_SECONDS = 10     # File download, setup, upload
        CONCURRENT_WORKERS = settings.max_workers  # Number of parallel workers (200)
        
        # With parallel processing, time = cold_start + (batches * time_per_batch) + overhead
        if total_items <= CONCURRENT_WORKERS:
            # All items processed in parallel - just one "batch"
            estimated_seconds = int(COLD_START_SECONDS + SECONDS_PER_BATCH + BASE_OVERHEAD_SECONDS)
        else:
            # Multiple batches needed
            batches = (total_items + CONCURRENT_WORKERS - 1) // CONCURRENT_WORKERS  # Ceiling division
            estimated_seconds = int(COLD_START_SECONDS + (batches * SECONDS_PER_BATCH) + BASE_OVERHEAD_SECONDS)
        
        estimated_minutes = estimated_seconds / 60
        
        logger.info(f"📊 Estimated processing time: {estimated_minutes:.1f} minutes ({estimated_seconds}s)")
        logger.info(f"📊 Processing {total_items} items with {CONCURRENT_WORKERS} workers in ~{batches if total_items > CONCURRENT_WORKERS else 1} batch(es)")
        
        # Get task ARN from ECS metadata endpoint
        task_arn = None
        cluster_name = os.getenv('ECS_CLUSTER_NAME', '')
        
        try:
            from urllib.request import urlopen
            # ECS metadata endpoint (available in Fargate tasks)
            metadata_uri = os.getenv('ECS_CONTAINER_METADATA_URI_V4')
            if metadata_uri:
                with urlopen(f"{metadata_uri}/task") as response:
                    task_metadata = json.loads(response.read().decode())
                    task_arn = task_metadata.get('TaskARN', '')
                    logger.info(f"📋 Task ARN: {task_arn}")
        except Exception as e:
            logger.warning(f"Failed to get task ARN from metadata: {e}")
        
        # Upload estimate file
        estimate_data = {
            "total_items": total_items,
            "estimated_seconds": estimated_seconds,
            "estimated_minutes": round(estimated_minutes, 1),
            "started_at": datetime.now().isoformat(),
            "filename": input_path.stem
        }
        
        # Add task tracking info if available
        if task_arn:
            estimate_data["task_arn"] = task_arn
        if cluster_name:
            estimate_data["cluster_name"] = cluster_name
        
        estimate_key = f"estimates/{input_path.stem}_estimate.json"
        storage.upload_json(estimate_data, estimate_key)
        logger.info(f"✅ Uploaded estimate to {estimate_key}")
        
    except Exception as e:
        logger.warning(f"Failed to calculate estimate: {e}. Proceeding without estimate.")
    
    # Wrap processing in try-except to clean up estimate on failure
    try:
        output_filename = f"{input_path.stem}_filled.xlsx"
        output_path = input_path.parent / output_filename
        
        result = await pipeline.process_file(
            input_file=input_path,
            output_file=output_path,
            namespace="",
            workers=settings.max_workers,
            filter_dict=filter_dict
        )
        
        s3_key = f"output/fills/{output_filename}"
        storage.upload_file(output_path, s3_key)
        logger.info(f"Uploaded result: {s3_key}")
        
        # SUCCESS: Update estimate with completion status (don't delete - frontend will handle it)
        if estimate_key and bucket_name:
            try:
                s3 = boto3.client('s3')
                # Read existing estimate
                estimate_obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(estimate_obj['Body'].read().decode('utf-8'))
                
                # Update with completion status
                estimate['complete'] = True
                estimate['success'] = True
                
                # Write back
                s3.put_object(
                    Bucket=bucket_name,
                    Key=estimate_key,
                    Body=json.dumps(estimate),
                    ContentType='application/json'
                )
                logger.info(f"✅ Updated estimate with success status: {estimate_key}")
            except Exception as update_error:
                logger.warning(f"Failed to update estimate (non-critical): {update_error}")
        
    except Exception as e:
        # ERROR: Update estimate with failure status
        if estimate_key and bucket_name:
            try:
                s3 = boto3.client('s3')
                # Read existing estimate
                estimate_obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(estimate_obj['Body'].read().decode('utf-8'))
                
                # Update with error status
                estimate['complete'] = True
                estimate['success'] = False
                estimate['error'] = str(e)
                
                # Write back
                s3.put_object(
                    Bucket=bucket_name,
                    Key=estimate_key,
                    Body=json.dumps(estimate),
                    ContentType='application/json'
                )
                logger.info(f"❌ Updated estimate with error status: {estimate_key}")
            except Exception as update_error:
                logger.error(f"Failed to update estimate with error: {update_error}")
        
        # Re-raise the original error
        logger.error(f"Processing failed: {e}")
        raise
    
    
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
