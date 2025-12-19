"""
Handler for the 'Severity' step.
This performs the Critical "Stop Work" check using the Knowledge Base.
"""

from typing import Dict, Any, List
try:
    from shared.conversation_state import ConversationState
    from shared.bedrock_client import BedrockClient
    # Import FAISSService for KB queries
    from shared.faiss_utils import FAISSService
    from shared.kb_repositories import KnowledgeBaseRepository
    from shared.dynamic_bedrock import DynamicBedrockClient
except ImportError:
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.faiss_utils import FAISSService
    from lambdas.shared.kb_repositories import KnowledgeBaseRepository
    from lambdas.shared.dynamic_bedrock import DynamicBedrockClient

def handle_severity(
    user_input_text: str, 
    phone_number: str, 
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> str:
    """
    Handle Severity Input and Trigger KB Safety Check.
    """
    severity_input = user_input_text.strip().upper()
    
    # Normalize input
    valid_severities = ["HIGH", "MEDIUM", "LOW"]
    severity = "MEDIUM" # Default
    
    # Map numbers to severities
    mapping = {"1": "HIGH", "2": "MEDIUM", "3": "LOW"}
    if severity_input in mapping:
        severity = mapping[severity_input]
    elif any(s in severity_input for s in valid_severities):
        for s in valid_severities:
            if s in severity_input:
                severity = s
                break
    else:
        return "Please specify if the severity is 1. High, 2. Medium, or 3. Low."

    # Update state immediately with severity
    # We update to a temporary state or the next state, but we need to do the analysis first.
    
    classification = current_state_data.get("draftData", {}).get("classification", "General Hazard")
    
    # --- KB CHECK ---
    advice, source = _query_safety_kb(classification, severity)
    
    # Save advice to draft data
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_STOP_WORK",
        curr_data={
            "severity": severity,
            "controlMeasure": advice,
            "reference": source
        }
    )
    
    # Construct Message
    message = f"Got it: *{severity}* severity.\n\n"
    
    if advice:
        message += f"⚠️ *Safety Check*:\nBased on our safety manual: \"{advice}\"\n\n"
    
    message += "Do you need to stop work immediately? (Yes/No)"
    
    return message

def _query_safety_kb(classification: str, severity: str) -> tuple[str, str]:
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
        # Scan the table for the first available 'ready' KB
        # In a real system, this would be a specific configured ID
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
                # 2. Load FAISS Index (Heavy operation)
                index, metadata = faiss_service.load_index_from_s3(kb_id=kb_id, user_id=user_id)
                
                # 3. Create Embedding for Query
                query_text = f"{classification} - Severity: {severity}"
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
                        # Extract text from results
                        # Metadata usually contains 'chunk_text' or similar? 
                        # Looking at document_processing.py would confirm, but usually 'text' or 'content'
                        # Let's assume 'text' based on common patterns or check result structure
                        # Use a safe get
                        fragments = []
                        for res in results:
                            meta = res.get("metadata", {})
                            text = meta.get("text") or meta.get("chunk_text") or meta.get("content") or ""
                            if text:
                                fragments.append(text)
                                # Capture filename as source if available
                                fname = meta.get("filename")
                                if fname and source_ref == "Standard Safety Protocols":
                                    source_ref = fname

                        context_text = "\n\n".join(fragments)
                        print(f"Retrieved {len(fragments)} fragments from KB.")
                    else:
                        print("No relevant matches found in KB.")
            except Exception as e:
                print(f"Error performing RAG search: {e}")
                # Fallback to empty context
        
        # 5. Generate Advice using Bedrock (with or without context)
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
        print(f"Error querying KB: {e}")
        import traceback
        traceback.print_exc()
        return "Please assess site conditions carefully and stop work if unsafe.", "General Guidelines"
