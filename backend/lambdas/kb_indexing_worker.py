"""SQS worker that processes documents into FAISS indexes."""

import json
import time
import uuid
from typing import Any, Dict

# Import from layer - optimized for AWS deployed structure
from lambdas.shared.document_processing import DocumentProcessingService
from lambdas.shared.faiss_utils import FAISSService
from lambdas.shared.kb_repositories import (
    KnowledgeBaseRepository,
    DocumentRepository,
)

# Lazy initialization to avoid errors at module load time
_document_repository = None
_knowledge_base_repository = None
_document_processing = None
_faiss_service = None


def _get_document_repository():
    """Lazy initialization of document repository."""
    global _document_repository
    if _document_repository is None:
        try:
            _document_repository = DocumentRepository()
        except ValueError as e:
            import os

            env_var = os.environ.get("DOCS_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: DOCS_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize DocumentRepository: {str(e)}")
    return _document_repository


def _get_knowledge_base_repository():
    """Lazy initialization of knowledge base repository."""
    global _knowledge_base_repository
    if _knowledge_base_repository is None:
        try:
            _knowledge_base_repository = KnowledgeBaseRepository()
        except ValueError as e:
            import os

            env_var = os.environ.get("KB_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: KB_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize KnowledgeBaseRepository: {str(e)}"
            )
    return _knowledge_base_repository


def _get_document_processing():
    """Lazy initialization of document processing service."""
    global _document_processing
    if _document_processing is None:
        try:
            _document_processing = DocumentProcessingService()
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize DocumentProcessingService: {str(e)}"
            )
    return _document_processing


def _get_faiss_service():
    """Lazy initialization of FAISS service."""
    global _faiss_service
    if _faiss_service is None:
        try:
            _faiss_service = FAISSService()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize FAISSService: {str(e)}")
    return _faiss_service


def handler(event, _context):
    """Entry point for the indexing worker.
    Processes multiple records in a batch but locks per-KB to ensure consistency.
    """
    records = event.get("Records", [])
    print(f"Processing {len(records)} indexing message(s)")

    # Group records by KB to potentially batch processing later (currently sequential per KB)
    # SQS batch size is 1 currently, but this prepares for higher throughput.
    for record in records:
        try:
            _process_record(record)
        except Exception as error:
            print(f"Failed to process record {record.get('messageId')}: {error}")
            # We catch exceptions here so one bad record doesn't fail the whole batch if we increase batchSize
            _mark_document_failed(record, str(error))
            # If we want to trigger DLQ for this specific message, we might need to raise
            # but for batch processing, handling partial failures is complex without batchItemFailures
            raise

    return {"statusCode": 200, "body": "Indexed documents"}


def _process_record(record: Dict[str, Any]):
    message = json.loads(record["body"])
    kb_id = message["kbId"]
    document_id = message["documentId"]
    s3_key = message["s3Key"]
    filename = message["filename"]
    file_type = message["fileType"]
    owner_id = message["userId"]
    embedding_model = message.get("embeddingModel", "amazon.titan-embed-text-v2:0")

    print(f"Indexing document {document_id} from KB {kb_id}")

    # Lazy initialize services
    document_processing = _get_document_processing()
    faiss_service = _get_faiss_service()
    document_repository = _get_document_repository()
    knowledge_base_repository = _get_knowledge_base_repository()

    # Import numpy only when needed (after services are initialized)
    import numpy as np

    # 1. Process document
    chunks = document_processing.download_and_process(
        s3_key=s3_key,
        document_id=document_id,
        filename=filename,
        file_type=file_type,
        kb_id=kb_id,
    )

    if not chunks:
        raise ValueError("Document produced no chunks")

    document_repository.update_status(
        kb_id=kb_id,
        document_id=document_id,
        status="embedding",
        chunk_count=len(chunks),
    )

    # 2. Generate embeddings
    embeddings = faiss_service.create_embeddings_batch(
        texts=[chunk["text"] for chunk in chunks],
        model_id=embedding_model,
        batch_size=25,
    )

    # 3. Acquire Index Lock (Optimistic Locking)
    lock_id = str(uuid.uuid4())
    max_retries = 5
    lock_acquired = False

    for attempt in range(max_retries):
        if knowledge_base_repository.update_index_lock(
            kb_id=kb_id, user_id=owner_id, lock_id=lock_id
        ):
            lock_acquired = True
            break
        # Linear backoff with jitter
        sleep_time = (1 * (attempt + 1)) + (0.1 * (attempt % 2))
        print(f"Lock acquisition failed, retrying in {sleep_time}s...")
        time.sleep(sleep_time)

    if not lock_acquired:
        raise RuntimeError(
            f"Failed to acquire index lock for KB {kb_id} after {max_retries} attempts"
        )

    try:
        # 4. Load, Update, Save Index
        try:
            existing_index, existing_metadata = faiss_service.load_index_from_s3(
                kb_id=kb_id, user_id=owner_id
            )
            existing_index.add(np.array(embeddings, dtype=np.float32))
            metadata = existing_metadata + chunks
            index = existing_index
            print(
                f"Appended {len(chunks)} chunks to existing index "
                f"(total {len(metadata)} vectors)"
            )
        except Exception as load_error:
            print(f"No existing index found ({load_error}), creating new index")
            index = faiss_service.create_index(embeddings)
            metadata = chunks

        faiss_service.save_index_to_s3(
            index=index,
            metadata=metadata,
            kb_id=kb_id,
            user_id=owner_id,
        )

        document_repository.update_status(
            kb_id=kb_id,
            document_id=document_id,
            status="indexed",
            chunk_count=len(chunks),
        )
        knowledge_base_repository.update(
            user_id=owner_id, kb_id=kb_id, updates={"indexStatus": "ready"}
        )
        print(f"Document {document_id} indexed successfully")

    finally:
        # 5. Release Lock
        knowledge_base_repository.release_index_lock(
            kb_id=kb_id, user_id=owner_id, lock_id=lock_id
        )


def _mark_document_failed(record: Dict[str, Any], message: str):
    try:
        payload = json.loads(record["body"])
        kb_id = payload.get("kbId")
        document_id = payload.get("documentId")
        if kb_id and document_id:
            document_repository = _get_document_repository()
            document_repository.update_status(
                kb_id=kb_id,
                document_id=document_id,
                status="failed",
                error_message=message,
            )
    except Exception as error:
        print(f"Failed to mark document as error: {error}")
