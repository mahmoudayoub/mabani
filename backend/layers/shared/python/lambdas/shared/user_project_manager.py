"""
User Project Manager interactions.
Manages persistent user preferences (last selected project) in DynamoDB.
"""

import os
import boto3
from typing import Optional
from botocore.exceptions import ClientError

class UserProjectManager:
    """Manages user project preferences in DynamoDB."""

    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.environ.get("USER_PROJECT_TABLE")
        if not self.table_name:
            self.table_name = "taskflow-backend-dev-user-projects"
            
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)

    def get_last_project(self, phone_number: str) -> Optional[str]:
        """
        Get the last selected project ID for a user.
        """
        try:
            # Table uses 'phoneNumber' as PK
            response = self.table.get_item(Key={"phoneNumber": phone_number})
            item = response.get("Item")
            return item.get("lastProjectId") if item else None
        except ClientError as e:
            print(f"Error fetching user project: {e}")
            return None

    def set_last_project(self, phone_number: str, project_id: str) -> None:
        """
        Save the selected project ID for a user.
        """
        try:
            self.table.put_item(
                Item={
                    "phoneNumber": phone_number,
                    "lastProjectId": project_id
                }
            )
        except ClientError as e:
            print(f"Error saving user project: {e}")
            raise
