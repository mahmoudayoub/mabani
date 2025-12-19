"""API handlers for knowledge base CRUD operations."""

import json
import os
import uuid
from typing import Any, Dict

# Import from layer - optimized for AWS deployed structure
# Layer structure: python/lambdas/shared/ -> lambdas.shared is available when deployed
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


# Lazy initialization to avoid errors at module load time
_kb_repository = None
_document_repository = None
_faiss_service = None

KB_BUCKET_NAME = os.environ.get("KB_BUCKET_NAME")
DOCUMENTS_PREFIX = "documents"


def _get_kb_repository():
    """Lazy initialization of knowledge base repository."""
    global _kb_repository
    if _kb_repository is None:
        try:
            _kb_repository = KnowledgeBaseRepository()
        except ValueError as e:
            # Environment variable missing - provide helpful error
            env_var = os.environ.get("KB_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: KB_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}. "
                f"Ensure serverless.yml environment variables are properly configured."
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
        except ValueError as e:
            env_var = os.environ.get("DOCS_TABLE_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: DOCS_TABLE_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize DocumentRepository: {str(e)}")
    return _document_repository


def _get_faiss_service():
    """Lazy initialization of FAISS service (only imported when needed)."""
    global _faiss_service
    if _faiss_service is None:
        try:
            # Import FAISS only when actually needed (avoids numpy import issues)
            # Optimized for AWS deployed structure
            from lambdas.shared.faiss_utils import FAISSService

            _faiss_service = FAISSService()
        except ValueError:
            env_var = os.environ.get("KB_BUCKET_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: KB_BUCKET_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize FAISSService: {str(e)}")
    return _faiss_service


def _require_authenticated_user(event: Dict[str, Any]):
    user_id = get_user_id(event)
    if not user_id:
        return None, create_error_response(401, "Unauthorized")

    return {"user_id": user_id}, None


@with_error_handling
def list_knowledge_bases(event, _context):
    """List knowledge bases owned by the caller."""
    user, error = _require_authenticated_user(event)
    if error:
        return error

    kb_repository = _get_kb_repository()
    knowledge_bases = kb_repository.list_for_user(user_id=user["user_id"])
    for kb in knowledge_bases:
        kb["shared"] = False
        kb["permission"] = "owner"

    return create_response(
        200,
        {
            "knowledgeBases": knowledge_bases,
            "total": len(knowledge_bases),
        },
    )


@with_error_handling
def get_knowledge_base(event, _context):
    """Fetch a single knowledge base."""
    user, error = _require_authenticated_user(event)
    if error:
        return error

    kb_id = (event.get("pathParameters") or {}).get("kbId")
    if not kb_id:
        return create_error_response(400, "kbId is required")

    kb_repository = _get_kb_repository()
    knowledge_base = kb_repository.get(user_id=user["user_id"], kb_id=kb_id)
    if not knowledge_base:
        return create_error_response(404, "Knowledge base not found")

    knowledge_base["shared"] = False
    knowledge_base["permission"] = "owner"
    return create_response(200, knowledge_base)


@with_error_handling
def create_knowledge_base(event, _context):
    """Create a new knowledge base."""
    user, error = _require_authenticated_user(event)
    if error:
        return error

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    body = json.loads(event["body"])
    name = (body.get("name") or "").strip()
    description = body.get("description", "").strip()
    embedding_model = body.get("embeddingModel", "amazon.titan-embed-text-v2:0").strip()

    if not name:
        return create_error_response(400, "Name is required")

    kb_repository = _get_kb_repository()
    knowledge_base = kb_repository.create(
        kb_id=str(uuid.uuid4()),
        user_id=user["user_id"],
        name=name,
        description=description,
        embedding_model=embedding_model or "amazon.titan-embed-text-v2:0",
    )

    return create_response(201, knowledge_base)


@with_error_handling
def update_knowledge_base(event, _context):
    """Update an existing knowledge base."""
    user, error = _require_authenticated_user(event)
    if error:
        return error

    kb_id = (event.get("pathParameters") or {}).get("kbId")
    if not kb_id:
        return create_error_response(400, "kbId is required")

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    kb_repository = _get_kb_repository()
    existing = kb_repository.get(user_id=user["user_id"], kb_id=kb_id)
    if not existing:
        return create_error_response(404, "Knowledge base not found")

    body = json.loads(event["body"])
    updates: Dict[str, Any] = {}
    if "name" in body:
        updates["name"] = body["name"]
    if "description" in body:
        updates["description"] = body["description"]

    if not updates:
        return create_error_response(400, "No updatable fields present")

    kb_repository = _get_kb_repository()
    updated = kb_repository.update(
        user_id=user["user_id"], kb_id=kb_id, updates=updates
    )
    return create_response(200, updated)


@with_error_handling
def delete_knowledge_base(event, _context):
    """Delete a knowledge base and all derived assets."""
    user, error = _require_authenticated_user(event)
    if error:
        return error

    kb_id = (event.get("pathParameters") or {}).get("kbId")
    if not kb_id:
        return create_error_response(400, "kbId is required")

    kb_repository = _get_kb_repository()
    knowledge_base = kb_repository.get(user_id=user["user_id"], kb_id=kb_id)
    if not knowledge_base:
        return create_error_response(404, "Knowledge base not found")

    _delete_documents_and_assets(kb_id=kb_id, owner_id=user["user_id"])

    kb_repository = _get_kb_repository()
    deleted = kb_repository.delete(user_id=user["user_id"], kb_id=kb_id)
    if not deleted:
        return create_error_response(500, "Failed to delete knowledge base")

    return create_response(200, {"message": "Knowledge base deleted successfully"})


def _delete_documents_and_assets(*, kb_id: str, owner_id: str):
    """Remove all document records, S3 objects, and FAISS indexes for a KB."""
    document_repository = _get_document_repository()
    s3_client = get_s3_client()
    faiss_service = _get_faiss_service()

    documents = document_repository.list_all(kb_id=kb_id)
    for document in documents:
        s3_key = document.get("s3Key")
        if s3_key:
            try:
                s3_client.delete_object(Bucket=KB_BUCKET_NAME, Key=s3_key)
            except Exception as error:
                print(f"Failed to delete object {s3_key}: {error}")

        document_repository.delete(kb_id=kb_id, document_id=document["documentId"])

    # Delete documents folder for the KB
    _delete_prefix_from_bucket(f"{DOCUMENTS_PREFIX}/{owner_id}/{kb_id}/")

    # Delete FAISS index artifacts
    try:
        faiss_service.delete_index_from_s3(kb_id=kb_id, user_id=owner_id)
    except Exception as error:
        print(f"Failed to delete FAISS index for {kb_id}: {error}")


def _delete_prefix_from_bucket(prefix: str):
    if not KB_BUCKET_NAME:
        return

    s3_client = get_s3_client()
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=KB_BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            try:
                s3_client.delete_object(Bucket=KB_BUCKET_NAME, Key=obj["Key"])
            except Exception as error:
                print(f"Failed to delete {obj['Key']}: {error}")
