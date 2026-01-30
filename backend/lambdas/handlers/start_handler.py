"""
Handler for the 'Start' state of the safety reporting workflow.
Processes the initial image upload and generates a provisional classification.
"""

import uuid
from typing import Dict, Any, Tuple
# Import shared utilities
# When deployed, these are in a layer or shared package. 
# We assume the router sets up sys.path or we use relative imports if possible.
try:
    from shared.bedrock_client import BedrockClient
    from shared.s3_client import S3Client
    from shared.conversation_state import ConversationState
    from shared.config_manager import ConfigManager
    from shared.user_project_manager import UserProjectManager
except ImportError:
    # Fallback for local testing
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.s3_client import S3Client
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.config_manager import ConfigManager
    from lambdas.shared.user_project_manager import UserProjectManager

def handle_start(
    user_input: Dict[str, Any], 
    phone_number: str, 
    state_manager: ConversationState
) -> str:
    """
    Handle the start of a new report (Workflow Step 1).
    
    Args:
        user_input: Parsed webhook data (body, media_url, etc.)
        phone_number: User's phone number
        state_manager: State manager instance
        
    Returns:
        String response message to send back to user
    """
    
    # 1. Validate Image
    image_url = user_input.get("imageUrl")
    description = user_input.get("description", "")
    
    if not image_url and not description:
        return "👋 Hi! To report a safety observation, please send a *photo* and a brief description."
        
    if not image_url:
        # Strict workflow A1: "Take photo of breach" is step 1.
        return "Please upload a *photo* of the observation to begin processing."

    # 2. Upload Image to S3
    s3_client = S3Client()
    request_id = str(uuid.uuid4())
    
    try:
        # We need a robust way to download/upload. S3Client.upload_image executes this.
        # It handles Twilio Auth internally if configured.
        print(f"Uploading image for {request_id}...")
        image_metadata = s3_client.upload_image(
            image_url=image_url,
            request_id=request_id,
            metadata={
                "sender": phone_number,
                "original_description": description or "No description provided"
            }
        )
        
        # 3. Analyze Image (Bedrock)
        bedrock_client = BedrockClient()
        
        # Download bytes back for analysis (inefficient but safe for now)
        # Alternatively, S3Client.upload_image could return the bytes, 
        # but it returns dict. Let's download it.
        image_bytes = s3_client.download_image(image_metadata["s3Key"])
        
        # Caption
        print("Captioning image...")
        caption = bedrock_client.caption_image(
            image_data=image_bytes,
            description=description or "Safety observation",
            report_type="HS" # Default to HS for now
        )
        
        # Initial Classification
        # We reuse 'classify_hazard_type' but we want a single primary one for the confirmation question.
        # Initial Classification
        print("Classifying observation...")
        
        # 1. High-level Observation Type
        observation_type = bedrock_client.classify_observation_type(
            description=description or caption,
            image_caption=caption
        )
        
        # 2. Detailed Hazard Category
        config = ConfigManager()
        taxonomy_list = config.get_options("HAZARD_TAXONOMY")
        
        # Format taxonomy for AI (handle dicts)
        if taxonomy_list and isinstance(taxonomy_list[0], dict):
            taxonomy_str = "\n".join([f"- {item['name']} ({item['category']})" for item in taxonomy_list])
        else:
            taxonomy_str = "\n".join(taxonomy_list)
        
        hazards = bedrock_client.classify_hazard_type(
            description=description or caption,
            image_caption=caption,
            severity="MEDIUM", # Placeholder
            report_type="HS",
            taxonomy=taxonomy_str
        )
        
        # Clean up response
        raw_hazard = hazards[0] if hazards else "Others"
        
        # If dict, extract name. If string, just use it.
        if isinstance(raw_hazard, dict):
            hazard_category = raw_hazard.get('name', raw_hazard.get('code', str(raw_hazard)))
        else:
            hazard_category = str(raw_hazard)
            
        # Remove any lingering " (Safety)" suffix if AI included it
        if " (" in hazard_category and ")" in hazard_category:
            hazard_category = hazard_category.split(" (")[0]
        
        # 4. Check Project Selection
        user_project_manager = UserProjectManager()
        last_project = user_project_manager.get_last_project(phone_number)
        
        draft_data = {
            "imageId": request_id,
            "imageKey": image_metadata["s3Key"],
            "imageCaption": caption,
            "s3Url": image_metadata["s3Url"],
            "imageUrl": image_metadata["httpsUrl"],
            "classification": hazard_category,
            "observationType": observation_type,
            "originalDescription": description
        }
        
        response_payload = {}
        next_state = "WAITING_FOR_CONFIRMATION"

        if last_project:
            # Case A: Auto-select Last Project
            print(f"Auto-selecting project: {last_project}")
            draft_data["projectId"] = last_project
            
            response_payload = {
                "text": f"Project: *{last_project}*\n\nI've analyzed the photo and identified a *{observation_type}* related to *{hazard_category}*.\n\nIs this correct?",
                "interactive": {
                    "type": "button",
                    "buttons": [
                        {"id": "yes", "title": "Yes"},
                        {"id": "no", "title": "No"}
                    ]
                }
            }
        else:
            # Case B: Prompt for Project
            print("No project selected. Prompting user...")
            next_state = "WAITING_FOR_PROJECT"
            
            # Get Projects list
            projects = config.get_options("PROJECTS")
            
            if not projects:
                # Fallback if no projects configured
                projects = ["Default Project"]
                
            # Create interactive list
            rows = [{"id": p, "title": p[:24]} for p in projects[:10]]
            
            response_payload = {
                "text": "Please select the *Project* for this report:",
                "interactive": {
                    "type": "list",
                    "body_text": "Choose from the active projects below:",
                    "button_text": "Select Project",
                    "items": rows
                }
            }

        # 5. Save State
        state_manager.start_conversation(
            phone_number=phone_number,
            report_id=request_id,
            draft_data=draft_data,
            start_state=next_state
        )
        
        # 6. Return Response
        return response_payload

    except Exception as e:
        print(f"Error in handle_start: {e}")
        import traceback
        traceback.print_exc()
        return "⚠️ I encountered an issue analyzing your photo. Please try again or contact support."
