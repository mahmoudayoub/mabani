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
except ImportError:
    # Fallback for local testing
    from lambdas.shared.bedrock_client import BedrockClient
    from lambdas.shared.s3_client import S3Client
    from lambdas.shared.conversation_state import ConversationState
    from lambdas.shared.config_manager import ConfigManager

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
        taxonomy_str = "\n".join(taxonomy_list)
        
        hazards = bedrock_client.classify_hazard_type(
            description=description or caption,
            image_caption=caption,
            severity="MEDIUM", # Placeholder
            report_type="HS",
            taxonomy=taxonomy_str
        )
        
        raw_hazard = hazards[0] if hazards else "A41 Others"
        
        # Clean up if it's a dict or complex structure
        if isinstance(raw_hazard, dict):
            # Prefer 'code' or 'name' or combined
            code = raw_hazard.get('code', '')
            name = raw_hazard.get('name', '')
            if code and name and code in name:
                hazard_category = name # Avoid "A2 Electrical Safety Electrical Safety"
            elif code and name:
                hazard_category = f"{code} {name}"
            else:
                hazard_category = code or name or str(raw_hazard)
        else:
            hazard_category = str(raw_hazard)
        
        # 4. Save Draft State
        draft_data = {
            "imageId": request_id,
            "imageKey": image_metadata["s3Key"],
            "imageCaption": caption,
            "s3Url": image_metadata["s3Url"],
            "imageUrl": image_metadata["httpsUrl"],
            "classification": hazard_category,      # Store detailed category here (e.g., A15 Working at Height)
            "observationType": observation_type,    # Store high-level type here (e.g., Unsafe Condition)
            "originalDescription": description
        }
        
        state_manager.start_conversation(
            phone_number=phone_number,
            report_id=request_id,
            draft_data=draft_data
        )
        
        # 5. Return Response
        return f"I've analyzed the photo and identified a *{observation_type}* related to *{hazard_category}*.\n\nIs this correct?\n(Reply *Yes* or *No*)"

    except Exception as e:
        print(f"Error in handle_start: {e}")
        import traceback
        traceback.print_exc()
        return "⚠️ I encountered an issue analyzing your photo. Please try again or contact support."
