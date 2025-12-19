"""API handlers for document management inside knowledge bases."""

import json
import os
import uuid
from typing import Any, Dict

import boto3

# Import from layer - optimized for AWS deployed structure
from lambdas.shared.kb_repositories import (
    KnowledgeBaseRepository,
    DocumentRepository,
)
from lambdas.shared.lambda_helpers import (
    with_error_handling,
    create_error_response,
    create_response,
    get_user_id,
    get_s3_client,
)


SUPPORTED_FILE_TYPES = {"pdf", "txt", "docx", "doc"}

# Lazy initialization to avoid errors at module load time
_kb_repository = None
_document_repository = None
_sqs_client = None

KB_BUCKET_NAME = os.environ.get("KB_BUCKET_NAME")
INDEXING_QUEUE_URL = os.environ.get("INDEXING_QUEUE_URL")


def _get_kb_repository():
    """Lazy initialization of knowledge base repository."""
    global _kb_repository
    if _kb_repository is None:
        try:
            _kb_repository = KnowledgeBaseRepository()
        except ValueError:
            env_var = os.environ.get("KB_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: KB_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to initialize KnowledgeBaseRepository: {str(e)}"
            )
    return _kb_repository


def _get_document_repository():
    """Lazy initialization of document repository."""
    global _document_repository
    if _document_repository is None:
        try:
            _document_repository = DocumentRepository()
        except ValueError:
            env_var = os.environ.get("DOCS_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: DOCS_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize DocumentRepository: {str(e)}")
    return _document_repository


def _get_sqs_client():
    """Lazy initialization of SQS client."""
    global _sqs_client
    if _sqs_client is None:
        _sqs_client = boto3.client("sqs")
    return _sqs_client


def _require_user_and_kb(event: Dict[str, Any]):
    user_id = get_user_id(event)
    if not user_id:
        return None, None, create_error_response(401, "Unauthorized")

    kb_id = (event.get("pathParameters") or {}).get("kbId")
    if not kb_id:
        return None, None, create_error_response(400, "kbId is required")

    kb_repository = _get_kb_repository()
    knowledge_base = kb_repository.get(user_id=user_id, kb_id=kb_id)
    if not knowledge_base:
        return None, None, create_error_response(404, "Knowledge base not found")

    return user_id, knowledge_base, None


@with_error_handling
def generate_upload_url(event, _context):
    """Generate a pre-signed S3 URL for uploading documents."""
    user_id, knowledge_base, error = _require_user_and_kb(event)
    if error:
        return error

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    body = json.loads(event["body"])
    filename = (body.get("filename") or "").strip()
    file_type = (body.get("fileType") or "").strip().lower()
    file_size = int(body.get("fileSize") or 0)

    if not filename or not file_type:
        return create_error_response(400, "filename and fileType are required")

    if file_type not in SUPPORTED_FILE_TYPES:
        return create_error_response(
            400,
            {
                "error": "Unsupported file type",
                "supportedTypes": sorted(SUPPORTED_FILE_TYPES),
            },
        )

    document_id = str(uuid.uuid4())
    owner_id = knowledge_base["userId"]
    s3_key = f"documents/{owner_id}/{knowledge_base['kbId']}/{document_id}/{filename}"

    # Map file types to proper MIME types
    mime_types = {
        "pdf": "application/pdf",
        "txt": "text/plain",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
    }
    content_type = mime_types.get(file_type, f"application/{file_type}")

    s3_client = get_s3_client()
    presigned_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": KB_BUCKET_NAME,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=900,
        HttpMethod="PUT",
    )

    return create_response(
        200,
        {
            "uploadUrl": presigned_url,
            "documentId": document_id,
            "s3Key": s3_key,
            "filename": filename,
            "fileType": file_type,
            "fileSize": file_size,
        },
    )


@with_error_handling
def confirm_document_upload(event, _context):
    """Persist document metadata and enqueue indexing."""
    user_id, knowledge_base, error = _require_user_and_kb(event)
    if error:
        return error

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    body = json.loads(event["body"])
    required_fields = ["documentId", "s3Key", "filename", "fileType"]
    missing = [field for field in required_fields if not body.get(field)]
    if missing:
        return create_error_response(
            400, f"Missing required fields: {', '.join(missing)}"
        )

    document_repository = _get_document_repository()
    document = document_repository.create(
        document_id=body["documentId"],
        kb_id=knowledge_base["kbId"],
        filename=body["filename"],
        file_type=body["fileType"],
        file_size=int(body.get("fileSize") or 0),
        s3_key=body["s3Key"],
        user_id=user_id,
    )

    kb_repository = _get_kb_repository()
    kb_repository.increment_document_stats(
        user_id=knowledge_base["userId"],
        kb_id=knowledge_base["kbId"],
        size=int(body.get("fileSize") or 0),
    )

    message = {
        "kbId": knowledge_base["kbId"],
        "documentId": document["documentId"],
        "s3Key": document["s3Key"],
        "filename": document["filename"],
        "fileType": document["fileType"],
        "userId": knowledge_base["userId"],
        "embeddingModel": knowledge_base.get(
            "embeddingModel", "amazon.titan-embed-text-v2:0"
        ),
    }

    sqs_client = _get_sqs_client()
    sqs_client.send_message(
        QueueUrl=INDEXING_QUEUE_URL, MessageBody=json.dumps(message)
    )

    document_repository.update_status(
        kb_id=knowledge_base["kbId"],
        document_id=document["documentId"],
        status="processing",
    )

    return create_response(
        201,
        {
            "message": "Document uploaded successfully. Indexing in progress.",
            "document": document,
        },
    )


@with_error_handling
def list_documents(event, _context):
    """List documents for a knowledge base."""
    _user_id, knowledge_base, error = _require_user_and_kb(event)
    if error:
        return error

    query_params = event.get("queryStringParameters") or {}
    limit = max(1, min(int(query_params.get("limit") or 50), 200))

    document_repository = _get_document_repository()
    result = document_repository.list(
        kb_id=knowledge_base["kbId"],
        limit=limit,
        exclusive_start_key=None,
    )

    return create_response(
        200,
        {
            "documents": result["items"],
            "count": len(result["items"]),
            "lastKey": None,
        },
    )


@with_error_handling
def delete_document(event, _context):
    """Delete a single document."""
    user_id, knowledge_base, error = _require_user_and_kb(event)
    if error:
        return error

    document_id = (event.get("pathParameters") or {}).get("documentId")
    if not document_id:
        return create_error_response(400, "documentId is required")

    document_repository = _get_document_repository()
    document = document_repository.get(
        kb_id=knowledge_base["kbId"], document_id=document_id
    )
    if not document:
        return create_error_response(404, "Document not found")

    if document.get("s3Key"):
        try:
            s3_client = get_s3_client()
            s3_client.delete_object(Bucket=KB_BUCKET_NAME, Key=document["s3Key"])
        except Exception as error:
            print(f"Failed to delete document object: {error}")

    deletion_success = document_repository.delete(
        kb_id=knowledge_base["kbId"], document_id=document_id
    )
    if not deletion_success:
        return create_error_response(500, "Failed to delete document record")

    kb_repository = _get_kb_repository()
    kb_repository.decrement_document_stats(
        user_id=knowledge_base["userId"],
        kb_id=knowledge_base["kbId"],
        size=document.get("fileSize", 0),
    )

    return create_response(200, {"message": "Document deleted successfully"})
