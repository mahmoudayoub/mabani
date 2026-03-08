
import os
import asyncio
import boto3
import json
import time
from urllib.parse import unquote

s3_client = boto3.client("s3")
lambda_client = boto3.client("lambda")
FILE_PROCESSING_BUCKET = os.environ.get("FILE_PROCESSING_BUCKET")

def create_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": True,
            "Access-Control-Allow-Methods": "DELETE,GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization"
        },
        "body": json.dumps(body)
    }


def _write_deletion_status(bucket, deletion_id, status_data):
    """Write deletion status marker to S3."""
    s3_client.put_object(
        Bucket=bucket,
        Key=f"deletion-status/{deletion_id}.json",
        Body=json.dumps(status_data),
        ContentType="application/json"
    )


# ============================================================
# STATUS ENDPOINT (shared across all delete types)
# ============================================================

def get_deletion_status(event, context):
    """
    Get the status of a deletion operation.
    Path params: deletion_id
    Query params: bucket_type = 'files' | 'pricecode' | 'pricecode-vector'
    """
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    deletion_id = path_params.get("deletion_id")

    if not deletion_id:
        return create_response(400, {"error": "Missing deletion_id"})

    deletion_id = unquote(deletion_id)

    # Determine which bucket to check based on query param
    query_params = event.get("queryStringParameters", {}) or {}
    bucket_type = query_params.get("bucket_type", "files")

    if bucket_type == "pricecode":
        bucket = os.environ.get("PRICECODE_BUCKET")
    elif bucket_type == "pricecode-vector":
        bucket = os.environ.get("PRICECODE_VECTOR_BUCKET")
    else:
        bucket = FILE_PROCESSING_BUCKET

    if not bucket:
        return create_response(500, {"error": f"Bucket not configured for type: {bucket_type}"})

    try:
        obj = s3_client.get_object(
            Bucket=bucket,
            Key=f"deletion-status/{deletion_id}.json"
        )
        status_data = json.loads(obj['Body'].read())
        return create_response(200, status_data)
    except s3_client.exceptions.NoSuchKey:
        return create_response(404, {"error": "Deletion status not found"})
    except Exception as e:
        return create_response(500, {"error": f"Failed to get status: {str(e)}"})


# ============================================================
# DISPATCHERS (fast — return 202 immediately)
# ============================================================

def dispatch_delete_datasheet(event, context):
    """
    Dispatch async deletion of a datasheet.
    Returns 202 with deletion_id for polling.
    """
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    sheet_name = path_params.get("sheet_name")

    if sheet_name:
        sheet_name = unquote(sheet_name)
    if not sheet_name:
        return create_response(400, {"error": "Missing sheet name"})

    deletion_id = f"ds_{int(time.time())}_{sheet_name.replace(' ', '_')}"

    # Write pending status
    _write_deletion_status(FILE_PROCESSING_BUCKET, deletion_id, {
        "status": "pending",
        "deletion_id": deletion_id,
        "set_name": sheet_name,
        "type": "datasheet",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    # Async invoke the worker
    worker_arn = os.environ.get("WORKER_LAMBDA_ARN_DATASHEET")
    if worker_arn:
        lambda_client.invoke(
            FunctionName=worker_arn,
            InvocationType="Event",
            Payload=json.dumps({
                **event,
                "deletion_id": deletion_id,
                "status_bucket": FILE_PROCESSING_BUCKET,
            })
        )

    return create_response(202, {
        "deletion_id": deletion_id,
        "message": f"Delete of '{sheet_name}' started",
        "bucket_type": "files"
    })


def dispatch_delete_price_code_set(event, context):
    """
    Dispatch async deletion of a price code set.
    Returns 202 with deletion_id for polling.
    """
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    set_name = path_params.get("set_name")

    if set_name:
        set_name = unquote(set_name)
    if not set_name:
        return create_response(400, {"error": "Missing set name"})

    bucket = os.environ.get("PRICECODE_BUCKET")
    if not bucket:
        return create_response(500, {"error": "PRICECODE_BUCKET not configured"})

    deletion_id = f"pc_{int(time.time())}_{set_name.replace(' ', '_')}"

    _write_deletion_status(bucket, deletion_id, {
        "status": "pending",
        "deletion_id": deletion_id,
        "set_name": set_name,
        "type": "pricecode",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    worker_arn = os.environ.get("WORKER_LAMBDA_ARN_PRICECODE")
    if worker_arn:
        lambda_client.invoke(
            FunctionName=worker_arn,
            InvocationType="Event",
            Payload=json.dumps({
                **event,
                "deletion_id": deletion_id,
                "status_bucket": bucket,
            })
        )

    return create_response(202, {
        "deletion_id": deletion_id,
        "message": f"Delete of '{set_name}' started",
        "bucket_type": "pricecode"
    })


def dispatch_delete_pricecode_vector_set(event, context):
    """
    Dispatch async deletion of a price code vector set.
    Returns 202 with deletion_id for polling.
    """
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    path_params = event.get("pathParameters", {}) or {}
    set_name = path_params.get("set_name")

    if set_name:
        set_name = unquote(set_name)
    if not set_name:
        return create_response(400, {"error": "Missing set name"})

    pcv_bucket = os.environ.get("PRICECODE_VECTOR_BUCKET")
    if not pcv_bucket:
        return create_response(500, {"error": "PRICECODE_VECTOR_BUCKET not configured"})

    deletion_id = f"pcv_{int(time.time())}_{set_name.replace(' ', '_')}"

    _write_deletion_status(pcv_bucket, deletion_id, {
        "status": "pending",
        "deletion_id": deletion_id,
        "set_name": set_name,
        "type": "pricecode-vector",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    })

    worker_arn = os.environ.get("WORKER_LAMBDA_ARN_PCV")
    if worker_arn:
        lambda_client.invoke(
            FunctionName=worker_arn,
            InvocationType="Event",
            Payload=json.dumps({
                **event,
                "deletion_id": deletion_id,
                "status_bucket": pcv_bucket,
            })
        )

    return create_response(202, {
        "deletion_id": deletion_id,
        "message": f"Delete of '{set_name}' started",
        "bucket_type": "pricecode-vector"
    })


# ============================================================
# WORKERS (existing logic, now write completion status to S3)
# ============================================================

def delete_datasheet(event, context):
    """
    Delete a datasheet (vectors + registry entry).
    Path params: sheet_name
    """
    # Handle CORS preflight if API Gateway passes generic proxy
    if event.get('httpMethod') == 'OPTIONS':
         return create_response(200, {})

    # Extract deletion tracking info (set by dispatcher)
    deletion_id = event.get("deletion_id")
    status_bucket = event.get("status_bucket", FILE_PROCESSING_BUCKET)

    path_params = event.get("pathParameters", {}) or {}
    sheet_name = path_params.get("sheet_name")
    
    # URL decode sheet_name
    if sheet_name:
        sheet_name = unquote(sheet_name)
    
    if not sheet_name:
        if deletion_id:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "error": "Missing sheet name"
            })
        return create_response(400, {"error": "Missing sheet name"})
        
    print(f"Deleting datasheet: {sheet_name}")

    # 1. Delete from S3 Vectors
    bucket_name = os.environ.get("S3_VECTORS_BUCKET", "almabani-vectors")
    index_name = os.environ.get("S3_VECTORS_INDEX_NAME", "almabani")
    region = os.environ.get("AWS_REGION", "eu-west-1")
    
    if bucket_name:
        try:
            from almabani.core.vector_store import VectorStoreService
            
            vector_store = VectorStoreService(
                bucket_name=bucket_name,
                region=region,
                index_name=index_name
            )
            
            async def run_delete():
                await vector_store.delete_by_metadata(
                    filter_dict={"sheet_name": {"$eq": sheet_name}}
                )
                
            asyncio.run(run_delete())
            print(f"Deleted vectors for sheet: {sheet_name} from index {index_name}")
        except Exception as e:
            print(f"Vector store deletion failed: {e}")
            if deletion_id:
                _write_deletion_status(status_bucket, deletion_id, {
                    "status": "error", "deletion_id": deletion_id,
                    "set_name": sheet_name, "error": f"Failed to delete vectors: {str(e)}"
                })
            return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})
    else:
        print("Skipping vector deletion (missing bucket name)")
            
    # 2. Update Registry in S3
    try:
        registry_key = "metadata/available_sheets.json"
        
        # Load existing (includes sheets AND groups)
        try:
            obj = s3_client.get_object(Bucket=FILE_PROCESSING_BUCKET, Key=registry_key)
            data = json.loads(obj['Body'].read())
            sheets = data.get("sheets", [])
            existing_groups = data.get("groups", [])  # Preserve groups!
        except s3_client.exceptions.NoSuchKey:
            sheets = []
            existing_groups = []
            
        # Update
        if sheet_name in sheets:
            sheets.remove(sheet_name)
            
            # Also remove deleted sheet from any groups
            for group in existing_groups:
                if sheet_name in group.get("sheets", []):
                    group["sheets"].remove(sheet_name)
            
            # Save back (preserve groups!)
            s3_client.put_object(
                Bucket=FILE_PROCESSING_BUCKET,
                Key=registry_key,
                Body=json.dumps({"sheets": sheets, "groups": existing_groups}, indent=2),
                ContentType="application/json"
            )
            print(f"Removed {sheet_name} from registry")
        else:
            print(f"Sheet {sheet_name} not found in registry")
            
    except Exception as e:
        if deletion_id:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "set_name": sheet_name, "error": f"Failed to update registry: {str(e)}"
            })
        return create_response(500, {"error": f"Failed to update registry: {str(e)}"})

    # Write completion status
    if deletion_id:
        _write_deletion_status(status_bucket, deletion_id, {
            "status": "complete", "deletion_id": deletion_id,
            "set_name": sheet_name, "message": f"Sheet {sheet_name} deleted successfully"
        })
        
    return create_response(200, {"message": f"Sheet {sheet_name} deleted successfully"})

def delete_price_code_set(event, context):
    """
    Delete a price code set from the SQLite lexical index + registry.

    The price code pipeline uses a SQLite index stored at
    ``metadata/pricecode_index.db`` in the PRICECODE_BUCKET.  Deleting a
    set means:
      1. Download the SQLite index from S3.
      2. Remove all rows for the given source_file from ``refs``,
         ``postings``, ``indexed_files``, and recompute ``df``.
      3. Re-upload the pruned index.
      4. Remove the source Excel from ``input/pricecode/index/``.
      5. Update ``metadata/available_price_codes.json`` registry.

    Path params: set_name (mapped from /pricecode/sets/{set_name})
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
         return create_response(200, {})

    # Extract deletion tracking info
    deletion_id = event.get("deletion_id")
    status_bucket = event.get("status_bucket")

    path_params = event.get("pathParameters", {}) or {}
    set_name = path_params.get("set_name")

    # URL decode
    if set_name:
        set_name = unquote(set_name)

    if not set_name:
        if deletion_id and status_bucket:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "error": "Missing set name"
            })
        return create_response(400, {"error": "Missing set name"})

    print(f"Deleting Price Code Set: {set_name}")

    bucket = os.environ.get("PRICECODE_BUCKET")
    if not bucket:
        if deletion_id and status_bucket:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "set_name": set_name, "error": "PRICECODE_BUCKET env var not set"
            })
        return create_response(500, {"error": "PRICECODE_BUCKET env var not set"})

    if not status_bucket:
        status_bucket = bucket

    # ── 1. Remove rows from SQLite index ────────────────────────────────
    db_s3_key = "metadata/pricecode_index.db"
    db_local = "/tmp/pricecode_index.db"
    try:
        s3_client.download_file(bucket, db_s3_key, db_local)
        print(f"Downloaded index from s3://{bucket}/{db_s3_key}")
    except s3_client.exceptions.ClientError as e:
        code = e.response.get("Error", {}).get("Code", "")
        if code in ("404", "NoSuchKey"):
            print("No existing index – nothing to prune")
        else:
            print(f"Failed to download index: {e}")
            if deletion_id:
                _write_deletion_status(status_bucket, deletion_id, {
                    "status": "error", "deletion_id": deletion_id,
                    "set_name": set_name, "error": f"Failed to download index: {str(e)}"
                })
            return create_response(500, {"error": f"Failed to download index: {str(e)}"})
        db_local = None

    if db_local:
        import sqlite3
        try:
            conn = sqlite3.connect(db_local)
            # Find ref_ids belonging to this source_file
            ref_ids = [
                r[0] for r in conn.execute(
                    "SELECT ref_id FROM refs WHERE source_file = ?", (set_name,)
                ).fetchall()
            ]
            before_count = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]

            if ref_ids:
                # Delete postings for those ref_ids
                # Use batches to avoid SQLite variable limit
                BATCH = 500
                for i in range(0, len(ref_ids), BATCH):
                    batch = ref_ids[i:i + BATCH]
                    ph = ",".join("?" for _ in batch)
                    conn.execute(f"DELETE FROM postings WHERE ref_id IN ({ph})", batch)

                # Delete refs
                conn.execute("DELETE FROM refs WHERE source_file = ?", (set_name,))

                # Delete from indexed_files
                conn.execute("DELETE FROM indexed_files WHERE source_file = ?", (set_name,))

                # Recompute df (document frequency) from remaining postings
                conn.execute("DELETE FROM df")
                conn.execute(
                    "INSERT INTO df (token, df) "
                    "SELECT token, COUNT(DISTINCT ref_id) FROM postings GROUP BY token"
                )

                # Recompute sheet_tokens signatures
                try:
                    conn.execute("DELETE FROM sheet_tokens")
                    # Recompute per-sheet token signatures
                    import math
                    stc = {}  # sheet -> {token: count}
                    sheet_sizes = {}
                    for _sheet, _tok, _cnt in conn.execute(
                        "SELECT r.sheet_name, p.token, COUNT(*) "
                        "FROM postings p JOIN refs r ON p.ref_id = r.ref_id "
                        "GROUP BY r.sheet_name, p.token"
                    ):
                        stc.setdefault(_sheet, {})[_tok] = _cnt
                        sheet_sizes[_sheet] = sheet_sizes.get(_sheet, 0) + _cnt
                    num_sheets = max(len(stc), 1)
                    tok_sheet_cnt = {}
                    for _sheet, _toks in stc.items():
                        for _tok in _toks:
                            tok_sheet_cnt[_tok] = tok_sheet_cnt.get(_tok, 0) + 1
                    sig_buf = []
                    for _sheet, _toks in stc.items():
                        _sz = max(sheet_sizes.get(_sheet, 1), 1)
                        scored = []
                        for _tok, _cnt in _toks.items():
                            _tf = _cnt / _sz
                            _idf = math.log(num_sheets / max(tok_sheet_cnt.get(_tok, 1), 1)) + 1.0
                            scored.append((_tok, _tf * _idf))
                        scored.sort(key=lambda x: x[1], reverse=True)
                        for _tok, _sc in scored[:50]:
                            sig_buf.append((_sheet, _tok, _sc))
                    conn.executemany("INSERT INTO sheet_tokens VALUES (?,?,?)", sig_buf)
                except Exception as e:
                    print(f"Warning: sheet_tokens recompute failed (non-fatal): {e}")

                # Update ref_count in meta
                after_count = conn.execute("SELECT COUNT(*) FROM refs").fetchone()[0]
                conn.execute(
                    "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                    ("ref_count", str(after_count)),
                )
                conn.commit()
                print(f"Pruned index: {before_count} -> {after_count} refs "
                      f"(removed {len(ref_ids)} rows for '{set_name}')")

                # VACUUM to reclaim space (shrink the .db file)
                conn.execute("VACUUM")
            else:
                after_count = before_count
                print(f"Source file '{set_name}' not found in index (0 rows matched)")

            conn.close()

            # Re-upload pruned index
            if ref_ids:
                s3_client.upload_file(db_local, bucket, db_s3_key)
                print(f"Re-uploaded pruned index to s3://{bucket}/{db_s3_key}")

        except Exception as e:
            print(f"SQLite prune failed: {e}")
            if deletion_id:
                _write_deletion_status(status_bucket, deletion_id, {
                    "status": "error", "deletion_id": deletion_id,
                    "set_name": set_name, "error": f"Failed to prune index: {str(e)}"
                })
            return create_response(500, {"error": f"Failed to prune index: {str(e)}"})

    # ── 2. Delete source Excel from S3 ──────────────────────────────────
    # The INDEX job stores reference files under input/pricecode/index/
    try:
        prefix = f"input/pricecode/index/"
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                stem = os.path.splitext(os.path.basename(key))[0]
                if stem == set_name or stem == f"ref_{set_name}":
                    s3_client.delete_object(Bucket=bucket, Key=key)
                    print(f"Deleted source file: s3://{bucket}/{key}")
    except Exception as e:
        print(f"Warning: failed to delete source Excel: {e}")

    # ── 3. Update registry ──────────────────────────────────────────────
    try:
        registry_key = "metadata/available_price_codes.json"

        # Load existing
        try:
            obj = s3_client.get_object(Bucket=bucket, Key=registry_key)
            data = json.loads(obj['Body'].read())
            codes = data.get("price_codes", [])
        except s3_client.exceptions.NoSuchKey:
            codes = []
        except Exception as e:
            print(f"Error reading registry: {e}")
            codes = []

        if set_name in codes:
            codes.remove(set_name)
            s3_client.put_object(
                Bucket=bucket,
                Key=registry_key,
                Body=json.dumps({"price_codes": codes}),
                ContentType="application/json"
            )
            print(f"Removed {set_name} from registry")
        else:
            print(f"Set {set_name} not found in registry")
    except Exception as e:
        if deletion_id:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "set_name": set_name, "error": f"Failed to update registry: {str(e)}"
            })
        return create_response(500, {"error": f"Failed to update registry: {str(e)}"})

    # Write completion status
    if deletion_id:
        _write_deletion_status(status_bucket, deletion_id, {
            "status": "complete", "deletion_id": deletion_id,
            "set_name": set_name, "message": f"Set {set_name} deleted successfully"
        })

    return create_response(200, {"message": f"Set {set_name} deleted successfully"})


def delete_pricecode_vector_set(event, context):
    """
    Delete a price-code vector set from S3 Vectors + registry.

    Path params: set_name (mapped from /pricecode-vector/sets/{set_name})

    Steps:
      1. Delete vectors from S3 Vectors index ``almabani-pricecode-vector``
         whose ``source_file`` metadata matches *set_name*.
      2. Delete source Excel from ``input/pricecode-vector/index/``.
      3. Update ``metadata/available_pricecode_vector.json`` registry.
    """
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return create_response(200, {})

    # Extract deletion tracking info
    deletion_id = event.get("deletion_id")
    status_bucket = event.get("status_bucket")

    path_params = event.get("pathParameters", {}) or {}
    set_name = path_params.get("set_name")

    if set_name:
        set_name = unquote(set_name)

    if not set_name:
        if deletion_id and status_bucket:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "error": "Missing set name"
            })
        return create_response(400, {"error": "Missing set name"})

    print(f"Deleting Price Code Vector Set: {set_name}")

    pcv_bucket = os.environ.get("PRICECODE_VECTOR_BUCKET")
    if not status_bucket:
        status_bucket = pcv_bucket

    # ── 1. Delete from S3 Vectors ───────────────────────────────────────
    bucket_name = os.environ.get("S3_VECTORS_BUCKET", "almabani-vectors")
    index_name = "almabani-pricecode-vector"
    region = os.environ.get("AWS_REGION", "eu-west-1")

    try:
        from almabani.core.vector_store import VectorStoreService

        vector_store = VectorStoreService(
            bucket_name=bucket_name,
            region=region,
            index_name=index_name,
        )

        async def _run_delete():
            return await vector_store.delete_by_metadata(
                filter_dict={"source_file": {"$eq": set_name}}
            )

        deleted = asyncio.run(_run_delete())
        print(f"Deleted {deleted} vectors for set '{set_name}' from index {index_name}")
    except Exception as e:
        print(f"Vector store deletion failed: {e}")
        if deletion_id and status_bucket:
            _write_deletion_status(status_bucket, deletion_id, {
                "status": "error", "deletion_id": deletion_id,
                "set_name": set_name, "error": f"Failed to delete vectors: {str(e)}"
            })
        return create_response(500, {"error": f"Failed to delete vectors: {str(e)}"})

    # ── 2. Delete source Excel from S3 ──────────────────────────────────
    if pcv_bucket:
        try:
            prefix = "input/pricecode-vector/index/"
            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=pcv_bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    stem = os.path.splitext(os.path.basename(key))[0]
                    if stem == set_name or stem == f"ref_{set_name}":
                        s3_client.delete_object(Bucket=pcv_bucket, Key=key)
                        print(f"Deleted source file: s3://{pcv_bucket}/{key}")
        except Exception as e:
            print(f"Warning: failed to delete source Excel: {e}")

    # ── 3. Update registry ──────────────────────────────────────────────
    if pcv_bucket:
        try:
            registry_key = "metadata/available_pricecode_vector.json"
            try:
                obj = s3_client.get_object(Bucket=pcv_bucket, Key=registry_key)
                data = json.loads(obj['Body'].read())
                sets_list = data.get("sets", [])
            except s3_client.exceptions.NoSuchKey:
                sets_list = []
            except Exception as e:
                print(f"Error reading registry: {e}")
                sets_list = []

            if set_name in sets_list:
                sets_list.remove(set_name)
                s3_client.put_object(
                    Bucket=pcv_bucket,
                    Key=registry_key,
                    Body=json.dumps({"sets": sets_list}, indent=2),
                    ContentType="application/json",
                )
                print(f"Removed '{set_name}' from pricecode-vector registry")
            else:
                print(f"Set '{set_name}' not found in registry")
        except Exception as e:
            if deletion_id and status_bucket:
                _write_deletion_status(status_bucket, deletion_id, {
                    "status": "error", "deletion_id": deletion_id,
                    "set_name": set_name, "error": f"Failed to update registry: {str(e)}"
                })
            return create_response(500, {"error": f"Failed to update registry: {str(e)}"})

    # Write completion status
    if deletion_id and status_bucket:
        _write_deletion_status(status_bucket, deletion_id, {
            "status": "complete", "deletion_id": deletion_id,
            "set_name": set_name, "message": f"Price Code Vector set '{set_name}' deleted successfully"
        })

    return create_response(200, {"message": f"Price Code Vector set '{set_name}' deleted successfully"})

