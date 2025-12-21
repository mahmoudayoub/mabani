"""API handler for querying knowledge bases via RAG."""

import json
from typing import Any, Dict, List

# Import from layer - optimized for AWS deployed structure
from lambdas.shared.dynamic_bedrock import DynamicBedrockClient
from lambdas.shared.kb_repositories import KnowledgeBaseRepository
from lambdas.shared.lambda_helpers import (
    with_error_handling,
    create_error_response,
    create_response,
    get_user_id,
)

# Lazy initialization to avoid errors at module load time
_kb_repository = None
_faiss_service = None
_bedrock_client = None


def _get_kb_repository():
    """Lazy initialization of knowledge base repository."""
    global _kb_repository
    if _kb_repository is None:
        try:
            _kb_repository = KnowledgeBaseRepository()
        except ValueError:
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
    return _kb_repository


def _get_faiss_service():
    """Lazy initialization of FAISS service."""
    global _faiss_service
    if _faiss_service is None:
        try:
            from lambdas.shared.faiss_utils import FAISSService

            _faiss_service = FAISSService()
        except ValueError:
            import os

            env_var = os.environ.get("KB_BUCKET_NAME", "NOT_SET")
            raise RuntimeError(
                f"Configuration error: KB_BUCKET_NAME environment variable is required. "
                f"Current value: {env_var}."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize FAISSService: {str(e)}")
    return _faiss_service


def _get_bedrock_client():
    """Lazy initialization of Bedrock client."""
    global _bedrock_client
    if _bedrock_client is None:
        try:
            _bedrock_client = DynamicBedrockClient()
        except Exception as e:
            raise RuntimeError(f"Failed to initialize DynamicBedrockClient: {str(e)}")
    return _bedrock_client


@with_error_handling
def query_knowledge_base(event, _context):
    """Run a semantic query against a knowledge base."""
    user_id = get_user_id(event)
    if not user_id:
        return create_error_response(401, "Unauthorized")

    kb_id = (event.get("pathParameters") or {}).get("kbId")
    if not kb_id:
        return create_error_response(400, "kbId is required")

    kb_repository = _get_kb_repository()
    # Use get_by_id to find KB regardless of owner
    knowledge_base = kb_repository.get_by_id(kb_id=kb_id)
    if not knowledge_base:
        return create_error_response(404, "Knowledge base not found")

    if knowledge_base.get("indexStatus") != "ready":
        return create_error_response(
            400, "Knowledge base index is not ready. Please add documents first."
        )

    if not event.get("body"):
        return create_error_response(400, "Request body is required")

    body = json.loads(event["body"])
    query_text = (body.get("query") or "").strip()
    model_id = (body.get("modelId") or "").strip()
    history = body.get("history") or []
    k = int(body.get("k") or 8)  # Increased default context window
    config = body.get("config") or {}
    distance_threshold = body.get("distanceThreshold")

    if not query_text:
        return create_error_response(400, "query is required")

    if not model_id:
        return create_error_response(400, "modelId is required")

    faiss_service = _get_faiss_service()
    try:
        index, metadata = faiss_service.load_index_from_s3(
            kb_id=kb_id, user_id=knowledge_base["userId"]
        )
    except Exception as error:
        return create_error_response(
            500, f"Failed to load knowledge base index: {error}"
        )

    query_embedding = faiss_service.create_embedding(
        text=query_text,
        model_id=knowledge_base.get("embeddingModel", "amazon.titan-embed-text-v2:0"),
    )

    results = faiss_service.search(
        index=index,
        metadata=metadata,
        query_embedding=query_embedding,
        k=max(1, min(k, 20)), # Allow up to 20 chunks
        distance_threshold=distance_threshold,
    )

    if not results:
        return create_response(
            200,
            {
                "answer": "No relevant information found in the knowledge base.",
                "sources": [],
                "retrievedChunks": 0,
            },
        )

    context, sources = _build_context(results)

    prompt = _build_prompt(query_text, context, sources, history)

    bedrock_client = _get_bedrock_client()
    try:
        answer = bedrock_client.invoke_model(
            prompt=prompt,
            model_id=model_id,
            temperature=float(config.get("temperature", 0.7)),
            max_tokens=int(config.get("maxTokens", 2048)),
            top_p=float(config.get("topP", 0.9)),
        )
    except Exception as error:
        return create_error_response(500, f"LLM invocation failed: {error}")

    return create_response(
        200,
        {
            "answer": answer,
            "sources": sources,
            "retrievedChunks": len(results),
            "query": query_text,
            "modelId": model_id,
        },
    )


def _build_context(results: List[Dict[str, Any]]):
    context_parts: List[str] = []
    sources: List[str] = []

    for rank, result in enumerate(results, start=1):
        metadata = result["metadata"]
        text = metadata.get("text", "")
        source = metadata.get("source", "Unknown")
        page = metadata.get("page")

        source_ref = f"{source}" + (
            f" (Page {page})" if page and page != "Unknown" else ""
        )
        context_parts.append(f"--- SOURCE {rank}: {source_ref} ---\n{text}\n")
        if source_ref not in sources:
            sources.append(source_ref)

    return "\n".join(context_parts), sources


def _build_prompt(
    query_text: str, context: str, sources: List[str], history: List[Dict[str, str]]
) -> str:
    sources_str = "\n".join([f"- {s}" for s in sources]) if sources else "N/A"

    history_str = ""
    if history:
        history_str = (
            "Conversation History:\n"
            + "\n".join(
                [
                    f"{msg.get('role', 'user').upper()}: {msg.get('content', '')}"
                    for msg in history[-5:]
                ]
            )
            + "\n\n"
        )

    return f"""You are a helpful and intelligent assistant. Your goal is to answer the user's question using the provided Knowledge Base context.

{history_str}Context from Knowledge Base:
{context}

Instructions:
1. Analyze the context above to find any information relevant to the user's question.
2. Even if the exact answer is not stated, summarize what the documents say about the topic.
3. If the documents contradict the premise of the question (e.g. user asks "how to do X" but documents say "X is prohibited"), explain that findings.
4. Only state "I cannot find the answer" if the context is completely irrelevant to the topic.
5. Cite your sources using [Source X] format.

Available Sources:
{sources_str}

User Question: {query_text}

Answer:"""
