"""
API Handler for Configuration Management.
Allows Admin/Managers to configure dropdown options (Locations, Acts, etc.).
"""

import json
from typing import Dict, Any
# Imports
try:
    from shared.config_manager import ConfigManager
    from shared.lambda_helpers import create_response, create_error_response, with_error_handling
except ImportError:
    from lambdas.shared.config_manager import ConfigManager
    from lambdas.shared.lambda_helpers import create_response, create_error_response, with_error_handling

@with_error_handling
def get_config(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    GET /config/{type}
    Retrieve configuration options for a specific type.
    """
    path_params = event.get("pathParameters") or {}
    config_type = path_params.get("type")
    
    if not config_type:
        return create_error_response(400, "Missing configuration type")
        
    manager = ConfigManager()
    options = manager.get_options(config_type)
    
    return create_response(200, {
        "type": config_type,
        "options": options
    })

@with_error_handling
def update_config(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    PUT /config/{type}
    Update configuration options for a specific type.
    Body: { "options": ["Option 1", "Option 2"] }
    """
    path_params = event.get("pathParameters") or {}
    config_type = path_params.get("type")
    
    if not config_type:
        return create_error_response(400, "Missing configuration type")
        
    try:
        body = json.loads(event.get("body", "{}"))
        options = body.get("options")
    except json.JSONDecodeError:
        return create_error_response(400, "Invalid JSON body")
        
    if not isinstance(options, list):
         return create_error_response(400, "'options' must be a list of strings")
         
    manager = ConfigManager()
    
    # Update DynamoDB
    # PK=CONFIG, SK={TYPE}
    try:
        manager.table.put_item(
            Item={
                "PK": "CONFIG",
                "SK": config_type.upper(),
                "values": options,
                "updatedAt": "TODO: timestamp" 
            }
        )
    except Exception as e:
        print(f"Error updating config: {e}")
        return create_error_response(500, "Failed to update configuration")
        
    return create_response(200, {
        "message": "Configuration updated successfully",
        "type": config_type,
        "options": options
    })
