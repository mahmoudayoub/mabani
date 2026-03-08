"""
Price Code Vector Worker – Fargate entry-point for the vector-based
price code service.

Modes
-----
INDEX      Parse a filled BOQ → embed items → store in S3 Vectors.
ALLOCATE   Parse a BOQ needing codes → embed → query S3 Vectors → fill.

Environment
-----------
S3_KEY              S3 key of the uploaded Excel file.
JOB_MODE            INDEX | ALLOCATE  (or auto-detect from path).
S3_BUCKET_NAME      Data bucket (for file I/O, registries, estimates).
S3_VECTORS_BUCKET   S3 Vectors bucket name.
OPENAI_API_KEY      Via SSM → container secrets.
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote_plus

import boto3

sys.path.insert(0, str(Path(__file__).parent))

from almabani.config.settings import get_settings
from almabani.core.embeddings import EmbeddingsService
from almabani.core.storage import get_storage
from almabani.core.vector_store import VectorStoreService
from almabani.pricecode_vector.indexer import PriceCodeVectorIndexer, PRICECODE_VECTOR_INDEX
from almabani.pricecode_vector.pipeline import PriceCodeVectorPipeline
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pricecode_vector_worker")


# ═══════════════════════════════════════════════════════════════════════
# Helper – shared service construction
# ═══════════════════════════════════════════════════════════════════════

def _build_services():
    """Return (settings, embeddings_service, vector_store)."""
    settings = get_settings()

    openai_async = AsyncOpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout,
        max_retries=0,
    )

    embeddings = EmbeddingsService(
        client=openai_async,
        model=settings.openai_embedding_model,
        rpm_limit=settings.embeddings_rpm,
        batch_size=settings.batch_size,
    )

    vector_store = VectorStoreService(
        bucket_name=settings.s3_vectors_bucket,
        region=settings.aws_region,
        index_name=PRICECODE_VECTOR_INDEX,
    )

    return settings, embeddings, vector_store


# ═══════════════════════════════════════════════════════════════════════
# INDEX mode
# ═══════════════════════════════════════════════════════════════════════

async def process_index(input_path: Path, storage):
    """
    Index ALL reference files currently under ``input/pricecode-vector/index/``.

    1. Download every .xlsx in that prefix.
    2. Delete any previous vectors for each source from S3 Vectors
       (so re-uploads overwrite cleanly).
    3. Parse, embed, upload.
    4. Update ``metadata/available_pricecode_vector.json`` registry.
    """
    logger.info(f"Starting INDEX job (triggered by {input_path.name})")

    settings, embeddings, vector_store = _build_services()
    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3 = boto3.client("s3")

    # ── 1. Ensure S3 Vectors index exists ──────────────────────────────
    await vector_store.create_index(
        dimension=settings.s3_vectors_dimension,
        metric="cosine",
        non_filterable_metadata_keys=[
            "text", "description", "price_code", "parent", "grandparent",
            "unit", "category_path", "item_code", "original_id", "row_index",
        ],
    )

    # ── 2. List every reference file under the index prefix ────────────
    ref_prefix = "input/pricecode-vector/index/"
    paginator = s3.get_paginator("list_objects_v2")
    ref_paths: list[tuple[str, Path]] = []  # (source_name, local_path)

    for page in paginator.paginate(Bucket=bucket_name, Prefix=ref_prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.lower().endswith(".xlsx"):
                local = Path(f"/tmp/ref_{Path(key).name}")
                storage.download_file(key, local)
                source_name = Path(key).stem
                if source_name.startswith("ref_"):
                    source_name = source_name[4:]
                ref_paths.append((source_name, local))
                logger.info(f"Downloaded reference file: {key}")

    if not ref_paths:
        logger.error("No reference Excel files found under " + ref_prefix)
        return

    # ── 3. Index each file (delete-then-insert) ───────────────────────
    indexer = PriceCodeVectorIndexer(embeddings, vector_store)
    total = 0
    source_names = []

    for source_name, local_path in ref_paths:
        # Remove previous vectors for this source so re-uploads are clean
        try:
            deleted = await vector_store.delete_by_metadata(
                {"source_file": {"$eq": source_name}}
            )
            if deleted:
                logger.info(f"Deleted {deleted} old vectors for '{source_name}'")
        except Exception as e:
            logger.warning(f"Pre-delete failed for '{source_name}' (non-fatal): {e}")

        result = await indexer.index_file(local_path, source_name=source_name)
        count = result.get("total_indexed", 0)
        total += count
        source_names.append(source_name)
        logger.info(f"Indexed '{source_name}': {count} vectors")

    # ── 4. Result metadata ─────────────────────────────────────────────
    result_meta = {
        "source_files": source_names,
        "indexed_count": total,
        "completed_at": datetime.now().isoformat(),
    }
    result_key = f"output/pricecode-vector/index/{input_path.stem}_indexed.json"
    storage.upload_json(result_meta, result_key)

    # ── 5. Update registry ─────────────────────────────────────────────
    _update_registry(s3, bucket_name, source_names)

    logger.info(f"INDEX complete: {total} vectors indexed from {len(ref_paths)} file(s)")


# ═══════════════════════════════════════════════════════════════════════
# ALLOCATE mode
# ═══════════════════════════════════════════════════════════════════════

async def process_allocate(input_path: Path, storage):
    """Allocate price codes to a BOQ using S3 Vectors similarity search."""
    logger.info(f"Starting ALLOCATE job for {input_path}")

    settings, embeddings, vector_store = _build_services()
    bucket_name = os.getenv("S3_BUCKET_NAME")
    s3 = boto3.client("s3")

    # ── 1. Processing estimate ──────────────────────────────────────────
    estimate_key = None
    try:
        import pandas as pd
        xls = pd.ExcelFile(input_path)
        df = pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        total_items = len(df)

        COLD_START_SECONDS = 15
        SECONDS_PER_ITEM = 0.15  # embedding + search per item
        BASE_OVERHEAD = 10
        estimated_seconds = max(
            30,
            COLD_START_SECONDS + int(total_items * SECONDS_PER_ITEM) + BASE_OVERHEAD,
        )

        task_arn = None
        try:
            from urllib.request import urlopen
            metadata_uri = os.getenv("ECS_CONTAINER_METADATA_URI_V4")
            if metadata_uri:
                with urlopen(f"{metadata_uri}/task") as resp:
                    task_arn = json.loads(resp.read().decode()).get("TaskARN", "")
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
        estimate_key = f"estimates/pcv_{input_path.stem}_estimate.json"
        storage.upload_json(estimate_data, estimate_key)
    except Exception as e:
        logger.warning(f"Failed to create estimate: {e}")

    # ── 2. Read source-files filter from S3 object metadata ──────────────
    s3_key = os.getenv("S3_KEY")
    if not s3_key or not bucket_name:
        raise RuntimeError(
            f"Missing S3 context. S3_KEY={bool(s3_key)}, "
            f"S3_BUCKET_NAME={bool(bucket_name)}"
        )

    try:
        head = s3.head_object(Bucket=bucket_name, Key=s3_key)
    except Exception as e:
        raise RuntimeError(
            f"Failed to read S3 metadata: s3://{bucket_name}/{s3_key}"
        ) from e

    metadata = head.get("Metadata", {}) or {}
    source_files_str = str(metadata.get("source-files", "")).strip()
    source_files = (
        [s.strip() for s in source_files_str.split(",") if s.strip()]
        if source_files_str
        else None
    )
    if source_files:
        logger.info(f"Source-file filter: {source_files}")
    else:
        logger.info("No source-file filter – searching all indexed data")

    # ── 3. Build pipeline ───────────────────────────────────────────────
    pipeline = PriceCodeVectorPipeline(
        embeddings_service=embeddings,
        vector_store=vector_store,
        top_k=settings.pricecode_vector_top_k,
        similarity_threshold=settings.pricecode_vector_threshold,
    )

    output_filename = f"{input_path.stem}_pricecode_vector.xlsx"
    output_path = input_path.parent / output_filename

    try:
        result = await pipeline.process_file(
            input_file=input_path,
            output_file=output_path,
            source_files=source_files,
        )

        # Upload result
        if output_path.exists():
            out_key = f"output/pricecode-vector/fills/{output_filename}"
            storage.upload_file(output_path, out_key)
            logger.info(f"Uploaded result: {out_key}")

        # Upload summary
        if result.get("summary_file"):
            sp = Path(result["summary_file"])
            if sp.exists():
                storage.upload_file(sp, f"output/pricecode-vector/fills/{sp.name}")

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

        logger.info(
            f"ALLOCATE complete: {result['matched']}/{result['total_items']} matched"
        )

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


# ═══════════════════════════════════════════════════════════════════════
# Registry helper
# ═══════════════════════════════════════════════════════════════════════

def _update_registry(s3, bucket_name: str, source_names: list[str]):
    """Maintain ``metadata/available_pricecode_vector.json``."""
    registry_key = "metadata/available_pricecode_vector.json"
    try:
        try:
            obj = s3.get_object(Bucket=bucket_name, Key=registry_key)
            registry = json.loads(obj["Body"].read().decode("utf-8"))
        except Exception:
            registry = {"sets": []}

        for name in source_names:
            if name not in registry["sets"]:
                registry["sets"].append(name)

        s3.put_object(
            Bucket=bucket_name,
            Key=registry_key,
            Body=json.dumps(registry, indent=2),
            ContentType="application/json",
        )
        logger.info(f"Updated pricecode-vector registry: {registry['sets']}")
    except Exception as e:
        logger.warning(f"Failed to update registry: {e}")


# ═══════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════

async def main():
    mode = os.getenv("JOB_MODE", "").upper()
    s3_key = os.getenv("S3_KEY")

    logger.info(f"Price Code Vector Worker started. Mode: {mode}, Key: {s3_key}")

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
            if "/pricecode-vector/index/" in s3_key:
                await process_index(local_input, storage)
            elif "/pricecode-vector/allocate/" in s3_key:
                await process_allocate(local_input, storage)
            else:
                logger.error(f"Unknown mode – cannot detect from path: {s3_key}")
                sys.exit(1)
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        sys.exit(1)

    logger.info("Job complete successfully.")


if __name__ == "__main__":
    asyncio.run(main())
