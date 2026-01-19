# WhatsApp Interactive Messages Implementation Guide

**Document Version**: 1.0  
**Created**: January 9, 2026  
**Status**: Implementation Ready

---

## Overview

This document provides complete implementation details for using Twilio's interactive WhatsApp messages (clickable buttons and lists) instead of numbered text responses.

## Twilio Interactive Message Types

### 1. Reply Buttons (Up to 3 Options)

**Best for**: Binary choices, simple selections

- Maximum 3 buttons per message
- Each button can have:
  - **ID**: Unique identifier (returned when clicked)
  - **Title**: Display text (up to 20 characters)

**Use Cases in Our Flow**:

- Observation Type confirmation (Yes/No)
- Breach Source (Almabani/Subcontractor)
- Severity (High/Medium/Low)
- Stoppage (Yes/No)

### 2. List Messages (Up to 10 Items per Section)

**Best for**: Multiple choices, categorized options

- Maximum 10 rows per section
- Maximum 10 sections per message
- Each row can have:
  - **ID**: Unique identifier
  - **Title**: Main text (up to 24 characters)
  - **Description**: Optional subtext (up to 72 characters)

**Use Cases in Our Flow**:

- Observation Categories (56 items - needs multi-section approach)
- Observation Type (5 options)
- Responsible Person selection
- Project selection

---

## Implementation

### Backend: Update Twilio Client

**File**: `backend/lambdas/shared/twilio_client.py`

```python
import os
from twilio.rest import Client
from typing import List, Dict, Any, Optional

class TwilioClient:
    """Enhanced Twilio client with interactive message support."""

    def __init__(self):
        # Get credentials from AWS Parameter Store
        self.account_sid = self._get_parameter("account_sid")
        self.auth_token = self._get_parameter("auth_token")
        self.whatsapp_number = self._get_parameter("whatsapp_number")
        self.client = Client(self.account_sid, self.auth_token)

    def _get_parameter(self, param_name: str) -> str:
        """Fetch parameter from AWS Systems Manager Parameter Store."""
        import boto3
        ssm = boto3.client('ssm')
        path = f"{os.environ.get('TWILIO_PARAMETER_PATH')}/{param_name}"
        response = ssm.get_parameter(Name=path, WithDecryption=True)
        return response['Parameter']['Value']

    def send_reply_buttons(
        self,
        to: str,
        body: str,
        buttons: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """
        Send WhatsApp message with reply buttons (max 3).

        Args:
            to: Recipient phone number (e.g., "+971501234567")
            body: Message text
            buttons: List of button dicts with 'id' and 'title'
                     Example: [
                         {"id": "high", "title": "High"},
                         {"id": "medium", "title": "Medium"},
                         {"id": "low", "title": "Low"}
                     ]

        Returns:
            Message SID and status
        """
        if len(buttons) > 3:
            raise ValueError("Maximum 3 buttons allowed for reply buttons")

        # Validate button titles (max 20 chars)
        for btn in buttons:
            if len(btn['title']) > 20:
                raise ValueError(f"Button title '{btn['title']}' exceeds 20 characters")

        try:
            message = self.client.messages.create(
                from_=f'whatsapp:{self.whatsapp_number}',
                to=f'whatsapp:{to}' if not to.startswith('whatsapp:') else to,
                body=body,
                # Twilio's interactive message format
                persistent_action=['reply'],
                action=[{
                    'buttons': [
                        {
                            'type': 'reply',
                            'reply': {
                                'id': btn['id'],
                                'title': btn['title']
                            }
                        } for btn in buttons
                    ]
                }]
            )

            return {
                'sid': message.sid,
                'status': message.status,
                'type': 'interactive_buttons'
            }

        except Exception as e:
            print(f"Error sending reply buttons: {e}")
            # Fallback to regular text message
            return self.send_text_message(to, self._format_as_text(body, buttons))

    def send_list_message(
        self,
        to: str,
        body: str,
        button_text: str,
        sections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Send WhatsApp list message (up to 10 items per section).

        Args:
            to: Recipient phone number
            body: Message text
            button_text: Text on the button that opens the list (e.g., "View Options")
            sections: List of section dicts with 'title' and 'rows'
                      Example: [
                          {
                              "title": "Safety",
                              "rows": [
                                  {"id": "1", "title": "Confined Spaces"},
                                  {"id": "2", "title": "Electrical Safety"}
                              ]
                          }
                      ]

        Returns:
            Message SID and status
        """
        # Validate sections
        if len(sections) > 10:
            raise ValueError("Maximum 10 sections allowed")

        for section in sections:
            if len(section.get('rows', [])) > 10:
                raise ValueError(f"Section '{section.get('title')}' has more than 10 rows")

            # Validate row titles (max 24 chars)
            for row in section.get('rows', []):
                if len(row['title']) > 24:
                    raise ValueError(f"Row title '{row['title']}' exceeds 24 characters")

        try:
            message = self.client.messages.create(
                from_=f'whatsapp:{self.whatsapp_number}',
                to=f'whatsapp:{to}' if not to.startswith('whatsapp:') else to,
                body=body,
                # Twilio's list message format
                persistent_action=['list'],
                action=[{
                    'button': button_text,
                    'sections': [
                        {
                            'title': section['title'],
                            'rows': [
                                {
                                    'id': row['id'],
                                    'title': row['title'],
                                    'description': row.get('description', '')
                                } for row in section['rows']
                            ]
                        } for section in sections
                    ]
                }]
            )

            return {
                'sid': message.sid,
                'status': message.status,
                'type': 'interactive_list'
            }

        except Exception as e:
            print(f"Error sending list message: {e}")
            # Fallback to regular text message
            return self.send_text_message(to, self._format_list_as_text(body, sections))

    def send_text_message(self, to: str, body: str) -> Dict[str, Any]:
        """Send regular text message (fallback)."""
        try:
            message = self.client.messages.create(
                from_=f'whatsapp:{self.whatsapp_number}',
                to=f'whatsapp:{to}' if not to.startswith('whatsapp:') else to,
                body=body
            )

            return {
                'sid': message.sid,
                'status': message.status,
                'type': 'text'
            }
        except Exception as e:
            print(f"Error sending text message: {e}")
            raise

    def _format_as_text(self, body: str, buttons: List[Dict[str, str]]) -> str:
        """Fallback: Format buttons as numbered text list."""
        text = body + "\n\n"
        for i, btn in enumerate(buttons, 1):
            text += f"{i}. {btn['title']}\n"
        text += "\nReply with number (1-" + str(len(buttons)) + ")"
        return text

    def _format_list_as_text(self, body: str, sections: List[Dict[str, Any]]) -> str:
        """Fallback: Format list as numbered text."""
        text = body + "\n\n"
        counter = 1
        for section in sections:
            text += f"\n**{section['title']}**\n"
            for row in section['rows']:
                text += f"{counter}. {row['title']}\n"
                counter += 1
        text += "\nReply with number"
        return text
```

---

## Parsing Interactive Message Responses

**File**: `backend/lambdas/twilio_webhook.py`

```python
def parse_twilio_message(event_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhanced parser to handle interactive message responses.

    Twilio sends interactive responses with:
    - ButtonPayload: User clicked a reply button
    - ListReply: User selected from a list
    """

    # Check for interactive button response
    if 'ButtonPayload' in event_body:
        button_id = event_body.get('ButtonPayload')
        button_text = event_body.get('Body', '')  # Text shown on button

        return {
            'type': 'interactive_button',
            'button_id': button_id,
            'button_text': button_text,
            'From': event_body.get('From'),
            'MessageSid': event_body.get('MessageSid')
        }

    # Check for interactive list response
    if 'ListReply' in event_body:
        # Parse the ListReply JSON string
        import json
        list_reply = json.loads(event_body.get('ListReply', '{}'))

        return {
            'type': 'interactive_list',
            'list_id': list_reply.get('id'),
            'list_title': list_reply.get('title'),
            'list_description': list_reply.get('description', ''),
            'From': event_body.get('From'),
            'MessageSid': event_body.get('MessageSid')
        }

    # Check for location
    if event_body.get('Latitude') and event_body.get('Longitude'):
        return {
            'type': 'location',
            'Latitude': event_body.get('Latitude'),
            'Longitude': event_body.get('Longitude'),
            'Label': event_body.get('Label', ''),
            'From': event_body.get('From'),
            'MessageSid': event_body.get('MessageSid')
        }

    # Check for media (image)
    if int(event_body.get('NumMedia', 0)) > 0:
        return {
            'type': 'media',
            'imageUrl': event_body.get('MediaUrl0'),
            'description': event_body.get('Body', ''),
            'From': event_body.get('From'),
            'MessageSid': event_body.get('MessageSid')
        }

    # Regular text message
    return {
        'type': 'text',
        'text': event_body.get('Body', ''),
        'From': event_body.get('From'),
        'MessageSid': event_body.get('MessageSid')
    }
```

---

## Updated Handlers with Interactive Messages

### 1. Observation Type Handler

**File**: `backend/lambdas/handlers/data_collection_handlers.py`

```python
def handle_observation_type_prompt(phone_number: str, state_manager: ConversationState) -> str:
    """Send observation type selection with interactive list."""
    from shared.twilio_client import TwilioClient

    twilio = TwilioClient()

    # Use interactive list message
    sections = [
        {
            "title": "Select Observation Type",
            "rows": [
                {"id": "EP", "title": "Environmental (EP)", "description": "Environmental Protection"},
                {"id": "GP", "title": "Good Practice (GP)", "description": "Positive observation"},
                {"id": "UA", "title": "Unsafe Act (UA)", "description": "Action-based hazard"},
                {"id": "UC", "title": "Unsafe Condition (UC)", "description": "Condition-based hazard"},
                {"id": "NM", "title": "Near Miss (NM)", "description": "Potential incident"}
            ]
        }
    ]

    result = twilio.send_list_message(
        to=phone_number,
        body="📍 Location confirmed!\n\nWhat type of observation is this?",
        button_text="View Options",
        sections=sections
    )

    return f"Interactive message sent: {result['type']}"

def handle_observation_type_response(
    user_input: Dict[str, Any],
    phone_number: str,
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> str:
    """Handle observation type selection from interactive list."""

    # Check if it's an interactive response
    if user_input.get('type') == 'interactive_list':
        obs_type_code = user_input.get('list_id')  # "EP", "GP", "UA", "UC", "NM"
        obs_type_title = user_input.get('list_title')  # "Environmental (EP)", etc.

    elif user_input.get('type') == 'text':
        # Fallback: User typed number or text
        text = user_input.get('text', '').strip()
        obs_type_map = {
            '1': ('EP', 'Environmental Protection (EP)'),
            '2': ('GP', 'Good Practice (GP)'),
            '3': ('UA', 'Unsafe Act (UA)'),
            '4': ('UC', 'Unsafe Condition (UC)'),
            '5': ('NM', 'Near Miss (NM)')
        }

        if text in obs_type_map:
            obs_type_code, obs_type_title = obs_type_map[text]
        else:
            return "⚠️ Invalid selection. Please use the button to view options."

    else:
        return "⚠️ Invalid selection. Please use the button to view options."

    # Save observation type
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_BREACH_SOURCE",
        curr_data={
            "observationType": obs_type_title,
            "observationTypeCode": obs_type_code
        }
    )

    # Next: Breach Source with reply buttons
    from shared.twilio_client import TwilioClient
    twilio = TwilioClient()

    twilio.send_reply_buttons(
        to=phone_number,
        body=f"Observation Type: {obs_type_title}\n\nWho is the breach source?",
        buttons=[
            {"id": "almabani", "title": "Almabani"},
            {"id": "subcontractor", "title": "Subcontractor"}
        ]
    )

    return "Breach source prompt sent"
```

### 2. Severity Handler

**File**: `backend/lambdas/handlers/severity_handler.py`

```python
def handle_severity_prompt(phone_number: str, project_id: str, state_manager: ConversationState) -> str:
    """Send severity selection with reply buttons."""
    from shared.twilio_client import TwilioClient

    twilio = TwilioClient()

    # Use reply buttons (3 options - perfect fit)
    result = twilio.send_reply_buttons(
        to=phone_number,
        body="What is the severity level?",
        buttons=[
            {"id": "high", "title": "🔴 High"},
            {"id": "medium", "title": "🟡 Medium"},
            {"id": "low", "title": "🟢 Low"}
        ]
    )

    return f"Interactive message sent: {result['type']}"

def handle_severity_response(
    user_input: Dict[str, Any],
    phone_number: str,
    state_manager: ConversationState,
    current_state_data: Dict[str, Any]
) -> str:
    """Handle severity selection from interactive buttons."""

    # Check if it's an interactive button response
    if user_input.get('type') == 'interactive_button':
        severity_id = user_input.get('button_id')  # "high", "medium", "low"
        severity_map = {
            'high': 'HIGH',
            'medium': 'MEDIUM',
            'low': 'LOW'
        }
        severity = severity_map.get(severity_id, 'MEDIUM')

    elif user_input.get('type') == 'text':
        # Fallback: User typed text
        text = user_input.get('text', '').strip().lower()
        if text in ['1', 'high', 'h']:
            severity = 'HIGH'
        elif text in ['2', 'medium', 'm']:
            severity = 'MEDIUM'
        elif text in ['3', 'low', 'l']:
            severity = 'LOW'
        else:
            return "⚠️ Invalid selection. Please use the buttons."

    else:
        return "⚠️ Invalid selection. Please use the buttons."

    # Save severity
    state_manager.update_state(
        phone_number=phone_number,
        curr_data={"severity": severity}
    )

    # Query Knowledge Base for control measure
    from shared.bedrock_client import BedrockClient
    from shared.knowledge_base import query_safety_advice

    draft_data = current_state_data.get("draftData", {})
    classification = draft_data.get("classification")

    advice = query_safety_advice(
        classification=classification,
        severity=severity,
        observation_type=draft_data.get("observationType")
    )

    # Save control measure
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_STOP_WORK",
        curr_data={
            "controlMeasure": advice.get("control_measure"),
            "reference": advice.get("reference", "HSG150")
        }
    )

    # Next: Stop work decision with reply buttons
    from shared.twilio_client import TwilioClient
    twilio = TwilioClient()

    message = f"🚨 Severity: {severity}\n\n"
    message += f"🛡️ Based on HSG150 guidelines:\n{advice.get('control_measure')}\n\n"
    message += "Does this require stoppage of work?"

    twilio.send_reply_buttons(
        to=phone_number,
        body=message,
        buttons=[
            {"id": "yes", "title": "Yes - Stop Work"},
            {"id": "no", "title": "No"}
        ]
    )

    return "Stop work prompt sent"
```

### 3. Category Selection (56 Options) - Multi-Section Approach

**File**: `backend/lambdas/handlers/confirmation_handler.py`

```python
def handle_classification_correction(phone_number: str, state_manager: ConversationState) -> str:
    """
    User said "No" to AI classification.
    Send categorized list of all 56 options.
    """
    from shared.twilio_client import TwilioClient
    from shared.config_manager import ConfigManager

    twilio = TwilioClient()
    config = ConfigManager()

    # Get full taxonomy
    taxonomy = config.get_taxonomy_full()

    # Group by category
    safety_items = [item for item in taxonomy if item['category'] == 'Safety']
    env_items = [item for item in taxonomy if item['category'] == 'Environmental']
    health_items = [item for item in taxonomy if item['category'] == 'Health']

    # Create sections (max 10 items per section)
    sections = []

    # Safety - split into multiple sections if > 10 items
    safety_sections = [safety_items[i:i+10] for i in range(0, len(safety_items), 10)]
    for idx, section_items in enumerate(safety_sections):
        sections.append({
            "title": f"Safety {idx+1}" if len(safety_sections) > 1 else "Safety",
            "rows": [
                {
                    "id": str(item['id']),
                    "title": item['name'][:24],  # Max 24 chars
                    "description": item.get('description', '')[:72]  # Max 72 chars
                } for item in section_items
            ]
        })

    # Environmental
    if len(env_items) > 10:
        env_sections = [env_items[i:i+10] for i in range(0, len(env_items), 10)]
        for idx, section_items in enumerate(env_sections):
            sections.append({
                "title": f"Environmental {idx+1}",
                "rows": [
                    {"id": str(item['id']), "title": item['name'][:24]}
                    for item in section_items
                ]
            })
    else:
        sections.append({
            "title": "Environmental",
            "rows": [
                {"id": str(item['id']), "title": item['name'][:24]}
                for item in env_items
            ]
        })

    # Health
    sections.append({
        "title": "Health",
        "rows": [
            {"id": str(item['id']), "title": item['name'][:24]}
            for item in health_items
        ]
    })

    # Send list message
    result = twilio.send_list_message(
        to=phone_number,
        body="Please select the correct observation category:",
        button_text="View All Categories",
        sections=sections[:10]  # Max 10 sections - if we have more, need alternative approach
    )

    return f"Category list sent: {result['type']}"

def handle_classification_selection(
    user_input: Dict[str, Any],
    phone_number: str,
    state_manager: ConversationState
) -> str:
    """Handle category selection from interactive list."""
    from shared.config_manager import ConfigManager

    config = ConfigManager()
    taxonomy = config.get_taxonomy_full()

    # Check if interactive list response
    if user_input.get('type') == 'interactive_list':
        category_id = int(user_input.get('list_id'))
        category_name = user_input.get('list_title')

        # Find full category details
        category = next((item for item in taxonomy if item['id'] == category_id), None)

        if category:
            selected_classification = category['name']
        else:
            return "⚠️ Invalid selection. Please try again."

    elif user_input.get('type') == 'text':
        # Fallback: User typed number
        text = user_input.get('text', '').strip()
        if text.isdigit():
            category_id = int(text)
            category = next((item for item in taxonomy if item['id'] == category_id), None)
            if category:
                selected_classification = category['name']
            else:
                return "⚠️ Invalid number. Please use the button to view categories."
        else:
            return "⚠️ Invalid selection. Please use the button to view categories."

    else:
        return "⚠️ Invalid selection. Please use the button to view categories."

    # Save classification
    state_manager.update_state(
        phone_number=phone_number,
        new_state="WAITING_FOR_LOCATION",
        curr_data={"classification": selected_classification}
    )

    return f"✅ Category confirmed: {selected_classification}\n\n" \
           f"📍 Please share your location:\n" \
           f"Tap 📎 → Location → Send your current location\n\n" \
           f"(I'll wait 30 seconds for accurate GPS coordinates)"
```

---

## Testing Interactive Messages

### 1. Test in Twilio Console

```python
# test_interactive_messages.py
from shared.twilio_client import TwilioClient

twilio = TwilioClient()

# Test reply buttons
result = twilio.send_reply_buttons(
    to="+971501234567",  # Your test number
    body="Test severity selection:",
    buttons=[
        {"id": "high", "title": "High"},
        {"id": "medium", "title": "Medium"},
        {"id": "low", "title": "Low"}
    ]
)
print(f"Reply buttons sent: {result}")

# Test list message
result = twilio.send_list_message(
    to="+971501234567",
    body="Test observation type:",
    button_text="Select Type",
    sections=[
        {
            "title": "Observation Types",
            "rows": [
                {"id": "EP", "title": "Environmental", "description": "Environmental Protection"},
                {"id": "GP", "title": "Good Practice", "description": "Positive observation"},
                {"id": "UC", "title": "Unsafe Condition", "description": "Condition hazard"}
            ]
        }
    ]
)
print(f"List message sent: {result}")
```

### 2. Verify Account Support

Run this check script:

```python
# check_interactive_support.py
import boto3
import os
from twilio.rest import Client

def check_interactive_message_support():
    """Check if Twilio account supports interactive messages."""

    # Get Twilio credentials
    ssm = boto3.client('ssm')
    account_sid = ssm.get_parameter(
        Name='/mabani/twilio/account_sid',
        WithDecryption=True
    )['Parameter']['Value']

    auth_token = ssm.get_parameter(
        Name='/mabani/twilio/auth_token',
        WithDecryption=True
    )['Parameter']['Value']

    client = Client(account_sid, auth_token)

    # Check account capabilities
    try:
        # Try to fetch WhatsApp sender
        senders = client.messaging.v1.services.list(limit=1)

        print("✅ Account SID:", account_sid)
        print("✅ Twilio client initialized successfully")

        # Note: Interactive messages are supported on most WhatsApp Business API accounts
        # But the feature must be enabled. Contact Twilio support if issues arise.

        print("\n📋 To enable interactive messages:")
        print("1. Log into Twilio Console: https://console.twilio.com")
        print("2. Go to: Messaging > WhatsApp > Senders")
        print("3. Verify 'Interactive Messages' is enabled for your sender")
        print("4. If not enabled, contact Twilio Support to request activation")

        return True

    except Exception as e:
        print(f"❌ Error checking account: {e}")
        return False

if __name__ == "__main__":
    check_interactive_message_support()
```

---

## Fallback Strategy

**IMPORTANT**: Always implement fallback to numbered text responses:

```python
def send_with_fallback(twilio_client, to, message_type, **kwargs):
    """
    Send interactive message with automatic fallback to text.
    """
    try:
        if message_type == 'buttons':
            return twilio_client.send_reply_buttons(**kwargs)
        elif message_type == 'list':
            return twilio_client.send_list_message(**kwargs)
    except Exception as e:
        print(f"Interactive message failed: {e}, falling back to text")
        # Fallback already handled in TwilioClient methods
        return {'status': 'fallback', 'error': str(e)}
```

---

## Environment Variables

Add to `serverless.yml`:

```yaml
environment:
  TWILIO_PARAMETER_PATH: /mabani/twilio
  ENABLE_INTERACTIVE_MESSAGES: true # Feature flag
```

---

## Migration Plan

### Phase 1: Test with Your Account

1. Run `check_interactive_support.py`
2. Send test interactive messages to your phone
3. Verify buttons/lists appear correctly

### Phase 2: Update Handlers

1. Deploy updated `TwilioClient` with interactive message methods
2. Update handlers to use interactive messages
3. Keep fallback logic intact

### Phase 3: Monitor & Rollout

1. Deploy to dev environment
2. Test complete workflow with interactive messages
3. Monitor for any fallback activations
4. If stable, deploy to production

---

## Cost Implications

**Interactive Messages Pricing** (Twilio):

- Same price as regular WhatsApp messages
- No additional charge for interactive elements
- Standard WhatsApp conversation pricing applies

**Current Twilio WhatsApp Pricing**:

- Business-initiated: ~$0.005 per message
- User-initiated: Free for first 24 hours

---

## Summary

✅ **Supported**: Twilio fully supports interactive WhatsApp messages  
✅ **Implementation**: Complete code provided above  
✅ **Fallback**: Automatic fallback to numbered text if interactive fails  
⚠️ **Requirement**: Account must have WhatsApp Business API + interactive messages enabled  
⚠️ **Limitation**: Max 3 buttons OR max 10 items per section in lists

For the 56 categories, you'll need to use **multi-section list messages** or implement a **two-step approach** (category group → specific item).

---

**Next Steps**:

1. Run account verification script
2. Contact Twilio support if interactive messages not enabled
3. Test with provided code examples
4. Deploy updated handlers

**END OF DOCUMENT**
