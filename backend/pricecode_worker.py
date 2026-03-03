"""
Price Code Worker – Fargate worker for price code indexing and allocation.

Modes
-----
INDEX     Build a SQLite lexical index from reference Excel files in S3.
ALLOCATE  Allocate price codes to BOQ items using lexical search + LLM.
"""

import os
import sys
import asyncio
import logging
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from urllib.parse import unquote_plus
import boto3

sys.path.insert(0, str(Path(__file__).parent))

from almabani.config.settings import get_settings
from almabani.core.storage import StorageService, get_storage
from almabani.pricecode.indexer import PriceCodeIndexer
from almabani.pricecode.lexical_search import LexicalMatcher, build_index
from almabani.pricecode.matcher import PriceCodeMatcher
from almabani.pricecode.pipeline import PriceCodePipeline
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pricecode_worker")


def get_services():
    """Initialise OpenAI async client (no embeddings needed)."""
    settings = get_settings()
    openai_async = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=settings.openai_max_retries,
    )
    return settings, openai_async


# ═══════════════════════════════════════════════════════════════════════
# INDEX mode
# ═══════════════════════════════════════════════════════════════════════

async def process_index(input_path: Path, storage):
    """
    Build a SQLite lexical index from ALL reference Excel files in S3,
    then upload it for use by ALLOCATE jobs.
    """
    logger.info(f"Starting INDEX job (triggered by {input_path.name})")

    settings = get_settings()
    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3 = boto3.client("s3")

    # 1. List every reference file under the index prefix
    ref_prefix = "input/pricecode/index/"
    paginator = s3.get_paginator("list_objects_v2")
    ref_paths: list[str] = []

    for page in paginator.paginate(Bucket=bucket_name, Prefix=ref_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".xlsx"):
                local = Path(f"/tmp/ref_{Path(key).name}")
                storage.download_file(key, local)
                ref_paths.append(str(local))
                logger.info(f"Downloaded reference file: {key}")

    if not ref_paths:
        logger.error("No reference Excel files found under " + ref_prefix)
        return

    # 2. Download existing index (if any) for append mode
    db_path = settings.pricecode_index_db
    db_s3_key = "metadata/pricecode_index.db"
    try:
        storage.download_file(db_s3_key, Path(db_path))
        logger.info(f"Downloaded existing index for append: {db_s3_key}")
    except Exception:
        logger.info("No existing index found – building from scratch")

    # 3. Build or append to SQLite index
    indexer = PriceCodeIndexer()
    count = indexer.index_from_excel(
        file_paths=[Path(p) for p in ref_paths],
        db_path=db_path,
        rebuild=False,
    )
    indexer.vacuum(db_path)

    # 4. Upload to well-known S3 key
    db_s3_key = "metadata/pricecode_index.db"
    storage.upload_file(Path(db_path), db_s3_key)
    logger.info(f"Uploaded SQLite index ({count:,} rows) to s3://{bucket_name}/{db_s3_key}")

    # 5. Result metadata
    result = {
        "source_files": [Path(p).stem for p in ref_paths],
        "indexed_count": count,
        "db_s3_key": db_s3_key,
        "completed_at": datetime.now().isoformat(),
    }
    result_key = f"output/pricecode/index/{input_path.stem}_indexed.json"
    storage.upload_json(result, result_key)

    # 6. Update available-price-codes registry
    if bucket_name:
        try:
            try:
                obj = s3.get_object(Bucket=bucket_name, Key="metadata/available_price_codes.json")
                registry = json.loads(obj["Body"].read().decode("utf-8"))
            except Exception:
                registry = {"price_codes": []}

            for p in ref_paths:
                name = Path(p).stem
                if name.startswith("ref_"):
                    name = name[4:]  # strip local-download prefix
                if name not in registry["price_codes"]:
                    registry["price_codes"].append(name)

            s3.put_object(
                Bucket=bucket_name,
                Key="metadata/available_price_codes.json",
                Body=json.dumps(registry, indent=2),
                ContentType="application/json",
            )
            logger.info(f"Updated price-code registry: {registry['price_codes']}")
        except Exception as e:
            logger.warning(f"Failed to update registry: {e}")

    logger.info(f"INDEX complete: {count:,} price codes indexed")


# ═══════════════════════════════════════════════════════════════════════
# ALLOCATE mode
# ═══════════════════════════════════════════════════════════════════════

async def process_allocate(input_path: Path, storage):
    """Allocate price codes to BOQ items using lexical search + LLM."""
    logger.info(f"Starting ALLOCATE job for {input_path}")

    settings, openai_async = get_services()
    bucket_name = os.getenv("S3_BUCKET_NAME")

    # ── 1. Download pre-built SQLite index ──────────────────────────────
    db_path = settings.pricecode_index_db
    db_s3_key = "metadata/pricecode_index.db"
    try:
        storage.download_file(db_s3_key, Path(db_path))
        logger.info(f"Downloaded lexical index: {db_s3_key}")
    except Exception as e:
        raise RuntimeError(
            f"Failed to download lexical index from s3://{bucket_name}/{db_s3_key}. "
            "Has the INDEX job been run? " + str(e)
        ) from e

    # ── 2. Create processing estimate ───────────────────────────────────
    estimate_key = None
    try:
        import pandas as pd

        xls = pd.ExcelFile(input_path)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        total_items = len(df)

        COLD_START_SECONDS = 15
        SECONDS_PER_BATCH = 4  # lexical is faster than embedding
        BASE_OVERHEAD = 10
        CONCURRENT = settings.pricecode_max_concurrent
        batches = (total_items + CONCURRENT - 1) // CONCURRENT
        estimated_seconds = max(30, COLD_START_SECONDS + batches * SECONDS_PER_BATCH + BASE_OVERHEAD)

        task_arn = None
        try:
            from urllib.request import urlopen

            metadata_uri = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
            if metadata_uri:
                with urlopen(f"{metadata_uri}/task") as response:
                    task_metadata = json.loads(response.read().decode())
                    task_arn = task_metadata.get("TaskARN", "")
        except Exception:
            pass

        estimate_data = {
            "total_items": total_items,
            "estimated_seconds": estimated_seconds,
            "started_at": datetime.utcnow().isoformat(),
            "filename": input_path.stem,
            "task_arn": task_arn,
            "cluster_name": os.getenv("ECS_CLUSTER_NAME", ""),
        }
        estimate_key = f"estimates/pc_{input_path.stem}_estimate.json"
        storage.upload_json(estimate_data, estimate_key)
    except Exception as e:
        logger.warning(f"Failed to create estimate: {e}")

    # ── 3. Read source-files filter from S3 object metadata ─────────────
    s3_key = os.getenv("S3_KEY")
    if not s3_key or not bucket_name:
        raise RuntimeError(
            "Missing required S3 context. "
            f"S3_KEY set={bool(s3_key)}, S3_BUCKET_NAME set={bool(bucket_name)}"
        )

    s3 = boto3.client("s3")
    try:
        head = s3.head_object(Bucket=bucket_name, Key=s3_key)
    except Exception as e:
        raise RuntimeError(
            f"Failed to read S3 metadata: s3://{bucket_name}/{s3_key}"
        ) from e

    metadata = head.get("Metadata", {}) or {}
    source_files_str = str(metadata.get("source-files", "")).strip()
    if not source_files_str:
        raise RuntimeError(
            "Required S3 metadata 'source-files' is missing. "
            "Refusing unfiltered search."
        )
    source_files = [s.strip() for s in source_files_str.split(",") if s.strip()]
    if not source_files:
        raise RuntimeError("source-files metadata produced no valid entries.")
    logger.info(f"Source-file filter: {source_files}")

    # ── 4. Build pipeline ───────────────────────────────────────────────
    lexical_matcher = await LexicalMatcher.create(
        db_path=db_path,
        source_files=source_files,
        max_candidates=settings.pricecode_max_candidates,
    )
    matcher = PriceCodeMatcher(
        async_openai_client=openai_async,
        lexical_matcher=lexical_matcher,
    )
    pipeline = PriceCodePipeline(matcher)

    output_filename = f"{input_path.stem}_pricecode.xlsx"
    output_path = input_path.parent / output_filename

    try:
        result = await pipeline.process_file(
            input_file=input_path,
            output_file=output_path,
            source_files=source_files,
        )

        # Upload result
        if output_path.exists():
            out_key = f"output/pricecode/fills/{output_filename}"
            storage.upload_file(output_path, out_key)
            logger.info(f"Uploaded result: {out_key}")

        # Upload summary
        if result.get("summary_file"):
            sp = Path(result["summary_file"])
            if sp.exists():
                storage.upload_file(sp, f"output/pricecode/fills/{sp.name}")

        # Update estimate
        if estimate_key and bucket_name:
            try:
                obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(obj["Body"].read().decode())
                estimate.update({"complete": True, "success": True, "result": result})
                s3.put_object(
                    Bucket=bucket_name, Key=estimate_key,
                    Body=json.dumps(estimate), ContentType="application/json",
                )
            except Exception as ue:
                logger.warning(f"Failed to update estimate: {ue}")

        logger.info(f"ALLOCATE complete: {result['matched']}/{result['total_items']} matched")

    except Exception as e:
        if estimate_key and bucket_name:
            try:
                obj = s3.get_object(Bucket=bucket_name, Key=estimate_key)
                estimate = json.loads(obj["Body"].read().decode())
                estimate.update({"complete": True, "success": False, "error": str(e)})
                s3.put_object(
                    Bucket=bucket_name, Key=estimate_key,
                    Body=json.dumps(estimate), ContentType="application/json",
                )
            except Exception:
                pass
        logger.error(f"Processing failed: {e}")
        raise
    finally:
        await lexical_matcher.close()


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

async def main():
    mode = os.getenv("JOB_MODE", "").upper()
    s3_key = os.getenv("S3_KEY")

    logger.info(f"Price Code Worker started. Mode: {mode}, Key: {s3_key}")

    if not s3_key:
        logger.error("No S3_KEY provided. Exiting.")
        sys.exit(1)

    storage = get_storage()

    local_filename = Path(s3_key).name
    local_input = Path(f"/tmp/{local_filename}")
    local_input.parent.mkdir(exist_ok=True, parents=True)

    logger.info(f"Downloading {s3_key} …")
    try:
        storage.download_file(s3_key, local_input)
    except Exception as e:
        logger.error(f"Failed to download: {e}")
        sys.exit(1)

    try:
        if mode == "INDEX":
            await process_index(local_input, storage)
        elif mode == "ALLOCATE":
            await process_allocate(local_input, storage)
        else:
            if "/index/" in s3_key:
                await process_index(local_input, storage)
            elif "/allocate/" in s3_key:
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
