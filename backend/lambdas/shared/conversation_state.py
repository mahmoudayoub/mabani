"""
Conversation state management for the interactive safety reporting workflow.
Handles DynamoDB operations for tracking user progress and data accumulation.
"""

import os
import json
import time
from typing import Dict, Any, Optional
import boto3
from botocore.exceptions import ClientError

class ConversationState:
    """Manages the conversation state in DynamoDB."""

    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize the ConversationState manager.

        Args:
            table_name: DynamoDB table name. Defaults to env var CONVERSATIONS_TABLE.
        """
        self.table_name = table_name or os.environ.get("CONVERSATIONS_TABLE")
        if not self.table_name:
            # Fallback for local testing or if not set, though ideally should be set
            self.table_name = "taskflow-backend-dev-conversations"
            
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)
        # TTL: 24 hours in seconds
        self.ttl_seconds = 24 * 60 * 60

    def get_state(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the current state for a phone number.

        Args:
            phone_number: The user's phone number (PK).

        Returns:
            Dictionary containing state data or None if no active session.
        """
        try:
            response = self.table.get_item(Key={"PK": f"PHONE#{phone_number}"})
            return response.get("Item")
        except ClientError as e:
            print(f"Error getting conversation state: {e}")
            return None

    def update_state(
        self, 
        phone_number: str, 
        new_state: str, 
        curr_data: Optional[Dict[str, Any]] = None,
        report_id: Optional[str] = None
    ) -> None:
        """
        Update the conversation state and accumulated data.

        Args:
            phone_number: The user's phone number.
            new_state: The new state to transition to.
            curr_data: Dictionary of data to merge/update into draftData.
            report_id: The ID of the report being created (optional).
        """
        timestamp = int(time.time())
        expires_at = timestamp + self.ttl_seconds

        try:
            # Read-Modify-Write approach to avoid complex UpdateExpressions and reserved keyword issues
            response = self.table.get_item(Key={"PK": f"PHONE#{phone_number}"})
            item = response.get("Item")

            if not item:
                # Fallback: Create new item if not exists (should have been started by start_conversation)
                item = {
                    "PK": f"PHONE#{phone_number}",
                    "draftData": {},
                }
                if report_id:
                    item["reportId"] = report_id

            # Update standard fields
            item["currentState"] = new_state
            item["lastUpdated"] = timestamp
            item["expiresAt"] = expires_at
            
            if report_id:
                item["reportId"] = report_id

            # Ensure draftData exists
            if "draftData" not in item:
                item["draftData"] = {}

            # Merge new data
            if curr_data:
                item["draftData"].update(curr_data)

            # Save back
            self.table.put_item(Item=item)
            print(f"State updated for {phone_number} -> {new_state}")

        except ClientError as e:
            print(f"Error updating state: {e}")
            raise

    def start_conversation(self, phone_number: str, report_id: str, draft_data: Dict[str, Any]) -> None:
        """
        Start a new conversation session, overwriting any previous one.

        Args:
            phone_number: User's phone number.
            report_id: New Report ID.
            draft_data: Initial data (e.g., initial classification).
        """
        timestamp = int(time.time())
        item = {
            "PK": f"PHONE#{phone_number}",
            "currentState": "WAITING_FOR_CONFIRMATION", # Default start state
            "reportId": report_id,
            "draftData": draft_data,
            "lastUpdated": timestamp,
            "expiresAt": timestamp + self.ttl_seconds
        }
        self.table.put_item(Item=item)
        print(f"Started new conversation for {phone_number}")

    def clear_state(self, phone_number: str) -> None:
        """
        Clear the conversation state (conversation complete).

        Args:
            phone_number: User's phone number.
        """
        try:
            self.table.delete_item(Key={"PK": f"PHONE#{phone_number}"})
            print(f"State cleared for {phone_number}")
        except ClientError as e:
            print(f"Error clearing state: {e}")
