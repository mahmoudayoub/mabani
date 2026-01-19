"""
Handler for the 'Safety Check' system step.
Includes KB Query logic.
"""

from typing import Tuple, Optional
try:
    from shared.bedrock_client import BedrockClient
    from shared.kb_repositories import KnowledgeBaseRepository
    from shared.faiss_utils import FAISSService
    from shared.dynamic_bedrock import DynamicBedrockClient
except ImportError:
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.kb_repositories import KnowledgeBaseRepository
    from lambdas.shared.faiss_utils import FAISSService
    from lambdas.shared.dynamic_bedrock import DynamicBedrockClient

def perform_safety_check(
    classification: str, 
    severity: str, 
    description: str = "", 
    caption: str = ""
) -> Tuple[str, str]:
    """
    Query the Knowledge Base for safety protocol.
    Returns (Advice, Source Reference)
    """
    try:
        # Initialize services
        kb_repo = KnowledgeBaseRepository()
        faiss_service = FAISSService()
        bedrock = DynamicBedrockClient()

        # 1. Find a usable Knowledge Base
        try:
            response = kb_repo.table.scan(
                FilterExpression="#st = :status",
                ExpressionAttributeNames={"#st": "status"},
                ExpressionAttributeValues={":status": "ready"},
                Limit=1
            )
            items = response.get("Items", [])
            kb_item = items[0] if items else None
        except Exception as e:
            print(f"Error scanning for KB: {e}")
            kb_item = None

        context_text = ""
        source_ref = "Standard Safety Protocols"

        if kb_item:
            kb_id = kb_item["kbId"]
            user_id = kb_item["userId"]
            kb_name = kb_item.get("name", "Safety Manual")
            print(f"Using Knowledge Base: {kb_name} ({kb_id})")

            try:
                # 2. Load FAISS Index
                index, metadata = faiss_service.load_index_from_s3(kb_id=kb_id, user_id=user_id)
                
                # 3. Create Embedding
                query_parts = [classification]
                if description: query_parts.append(description)
                if caption: query_parts.append(caption)
                query_parts.append(f"Severity: {severity}")
                
                query_text = " - ".join(query_parts)
                print(f"RAG Query: {query_text}")
                
                query_embedding = faiss_service.create_embedding(text=query_text)
                
                if query_embedding:
                    # 4. Search Index
                    results = faiss_service.search(
                        index=index,
                        metadata=metadata,
                        query_embedding=query_embedding,
                        k=2 
                    )
                    
                    if results:
                        fragments = []
                        for res in results:
                            meta = res.get("metadata", {})
                            text = meta.get("text") or meta.get("chunk_text") or meta.get("content") or ""
                            if text:
                                fragments.append(text)
                                fname = meta.get("filename")
                                page = meta.get("page_number") or meta.get("page")
                                
                                if fname and source_ref == "Standard Safety Protocols":
                                    if page:
                                        source_ref = f"{fname} (Page {page})"
                                    else:
                                        source_ref = fname

                        context_text = "\n\n".join(fragments)
                        print(f"Retrieved {len(fragments)} fragments from KB.")
                    else:
                        print("No relevant matches found in KB.")
            except Exception as e:
                print(f"Error performing RAG search: {e}")
        
        # 5. Generate Advice using Bedrock
        prompt = f"""You are a Safety Officer. 
        
        System Context:
        {context_text if context_text else "No specific safety manual pages found."}
        
        Situation: {classification}
        Severity: {severity}
        
        Instructions:
        1. Access the provided System Context to find specific procedures for this situation.
        2. If relevant procedures are found, summarize the immediate action required strictly based on that context.
        3. If no context is found, provide standard general safety advice based on the situation and severity.
        4. Keep the advice concise (1-2 sentences).
        5. Warn about "Stop Work" if the severity is High.
        """
        
        response_text = bedrock.invoke_model(
            prompt=prompt,
            model_id="amazon.nova-lite-v1:0"
        )
        
        return response_text, source_ref

    except Exception as e:
        print(f"Error checking safety manual: {e}")
        return "Please assess site conditions carefully and stop work if unsafe.", "General Guidelines"
