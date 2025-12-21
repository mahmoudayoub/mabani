"""Repositories for knowledge base and document persistence."""

import os
import time
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key


class KnowledgeBaseRepository:
    """DynamoDB repository for knowledge bases."""

    KB_ID_INDEX = "KbIdIndex"
    USER_CREATED_AT_INDEX = "UserCreatedAtIndex"

    def __init__(self):
        table_name = os.environ.get("KB_TABLE_NAME")
        if not table_name:
            raise ValueError("KB_TABLE_NAME environment variable is required")

        self.table = boto3.resource("dynamodb").Table(table_name)

    def update_index_lock(
        self, *, kb_id: str, user_id: str, lock_id: str, ttl_seconds: int = 300
    ) -> bool:
        """
        Acquire a lock for updating the KB index.
        Returns True if lock acquired, False otherwise.
        """
        timestamp = int(time.time() * 1000)
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="SET indexLock = :lock, indexLockTime = :time",
                ConditionExpression=(
                    "attribute_not_exists(indexLock) OR "
                    "indexLock = :empty OR "
                    "indexLockTime < :expiry"
                ),
                ExpressionAttributeValues={
                    ":lock": lock_id,
                    ":time": timestamp,
                    ":empty": "",
                    ":expiry": timestamp - (ttl_seconds * 1000),
                },
            )
            return True
        except Exception:
            return False

    def release_index_lock(self, *, kb_id: str, user_id: str, lock_id: str):
        """Release the KB index lock."""
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="REMOVE indexLock, indexLockTime",
                ConditionExpression="indexLock = :lock",
                ExpressionAttributeValues={":lock": lock_id},
            )
        except Exception:
            pass

    def create(
        self,
        *,
        kb_id: str,
        user_id: str,
        name: str,
        description: str,
        embedding_model: str,
    ) -> Dict[str, Any]:
        """Create a new knowledge base record."""
        timestamp = int(time.time() * 1000)

        item = {
            "kbId": kb_id,
            "userId": user_id,
            "name": name,
            "description": description,
            "embeddingModel": embedding_model,
            "status": "ready",
            "documentCount": 0,
            "totalSize": 0,
            "indexStatus": "empty",
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

        self.table.put_item(Item=item)
        return item

    def get(self, *, user_id: str, kb_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.get_item(Key={"userId": user_id, "kbId": kb_id})
        return response.get("Item")

    def get_by_id(self, kb_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.query(
            IndexName=self.KB_ID_INDEX, KeyConditionExpression=Key("kbId").eq(kb_id)
        )
        items = response.get("Items", [])
        return items[0] if items else None

    def list_for_user(self, *, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        response = self.table.query(
            KeyConditionExpression=Key("userId").eq(user_id),
            IndexName=self.USER_CREATED_AT_INDEX,
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])

    def list_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all knowledge bases (scan operation)."""
        # Scan is used because we want everything. 
        # In a very large system we might need pagination or a global index, but for this scale scan is fine.
        response = self.table.scan(Limit=limit)
        return response.get("Items", [])

    def update(
        self, *, user_id: str, kb_id: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        timestamp = int(time.time() * 1000)
        updates = {**updates, "updatedAt": timestamp}

        update_expression = []
        expression_attribute_names = {}
        expression_attribute_values = {}

        for key, value in updates.items():
            attr_name = f"#{key}"
            attr_value = f":{key}"
            update_expression.append(f"{attr_name} = {attr_value}")
            expression_attribute_names[attr_name] = key
            expression_attribute_values[attr_value] = value

        response = self.table.update_item(
            Key={"userId": user_id, "kbId": kb_id},
            UpdateExpression="SET " + ", ".join(update_expression),
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW",
        )
        return response.get("Attributes", {})

    def delete(self, *, user_id: str, kb_id: str) -> bool:
        try:
            self.table.delete_item(Key={"userId": user_id, "kbId": kb_id})
            return True
        except Exception as error:
            print(f"Failed to delete knowledge base {kb_id}: {error}")
            return False

    def increment_document_stats(self, *, user_id: str, kb_id: str, size: int):
        self.table.update_item(
            Key={"userId": user_id, "kbId": kb_id},
            UpdateExpression=(
                "ADD documentCount :inc, totalSize :size SET updatedAt = :timestamp"
            ),
            ExpressionAttributeValues={
                ":inc": 1,
                ":size": size,
                ":timestamp": int(time.time() * 1000),
            },
        )

    def decrement_document_stats(self, *, user_id: str, kb_id: str, size: int):
        self.table.update_item(
            Key={"userId": user_id, "kbId": kb_id},
            UpdateExpression=(
                "ADD documentCount :dec, totalSize :size SET updatedAt = :timestamp"
            ),
            ExpressionAttributeValues={
                ":dec": -1,
                ":size": -size,
                ":timestamp": int(time.time() * 1000),
            },
        )


class DocumentRepository:
    """DynamoDB repository for documents."""

    KB_UPLOADED_AT_INDEX = "KbUploadedAtIndex"

    def __init__(self):
        table_name = os.environ.get("DOCS_TABLE_NAME")
        if not table_name:
            raise ValueError("DOCS_TABLE_NAME environment variable is required")

        self.table = boto3.resource("dynamodb").Table(table_name)

    def create(
        self,
        *,
        document_id: str,
        kb_id: str,
        filename: str,
        file_type: str,
        file_size: int,
        s3_key: str,
        user_id: str,
    ) -> Dict[str, Any]:
        timestamp = int(time.time() * 1000)
        item = {
            "documentId": document_id,
            "kbId": kb_id,
            "filename": filename,
            "fileType": file_type,
            "fileSize": file_size,
            "s3Key": s3_key,
            "userId": user_id,
            "status": "uploaded",
            "chunkCount": 0,
            "uploadedAt": timestamp,
            "processedAt": 0,
        }
        self.table.put_item(Item=item)
        return item

    def get(self, *, kb_id: str, document_id: str) -> Optional[Dict[str, Any]]:
        response = self.table.get_item(Key={"kbId": kb_id, "documentId": document_id})
        return response.get("Item")

    def list(
        self,
        *,
        kb_id: str,
        limit: int = 100,
        exclusive_start_key: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {
            "KeyConditionExpression": Key("kbId").eq(kb_id),
            "IndexName": self.KB_UPLOADED_AT_INDEX,
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if exclusive_start_key:
            params["ExclusiveStartKey"] = exclusive_start_key

        response = self.table.query(**params)
        return {
            "items": response.get("Items", []),
            "last_key": response.get("LastEvaluatedKey"),
        }

    def list_all(self, *, kb_id: str) -> List[Dict[str, Any]]:
        documents: List[Dict[str, Any]] = []
        last_evaluated_key = None

        while True:
            response = self.list(kb_id=kb_id, exclusive_start_key=last_evaluated_key)
            documents.extend(response["items"])
            last_evaluated_key = response["last_key"]
            if not last_evaluated_key:
                break

        return documents

    def update_index_lock(
        self, *, kb_id: str, user_id: str, lock_id: str, ttl_seconds: int = 300
    ) -> bool:
        """
        Acquire a lock for updating the KB index.
        Returns True if lock acquired, False otherwise.
        """
        timestamp = int(time.time() * 1000)
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="SET indexLock = :lock, indexLockTime = :time",
                ConditionExpression=(
                    "attribute_not_exists(indexLock) OR "
                    "indexLock = :empty OR "
                    "indexLockTime < :expiry"
                ),
                ExpressionAttributeValues={
                    ":lock": lock_id,
                    ":time": timestamp,
                    ":empty": "",
                    ":expiry": timestamp - (ttl_seconds * 1000),
                },
            )
            return True
        except Exception:
            return False

    def release_index_lock(self, *, kb_id: str, user_id: str, lock_id: str):
        """Release the KB index lock."""
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="REMOVE indexLock, indexLockTime",
                ConditionExpression="indexLock = :lock",
                ExpressionAttributeValues={":lock": lock_id},
            )
        except Exception:
            pass

    def update_status(
        self,
        *,
        kb_id: str,
        document_id: str,
        status: str,
        chunk_count: int = 0,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        timestamp = int(time.time() * 1000)

        update_expression = "SET #status = :status, processedAt = :timestamp"
        expression_attribute_names = {"#status": "status"}
        expression_attribute_values: Dict[str, Any] = {
            ":status": status,
            ":timestamp": timestamp,
        }

        if chunk_count > 0:
            update_expression += ", chunkCount = :chunk_count"
            expression_attribute_values[":chunk_count"] = chunk_count

        if error_message:
            update_expression += ", errorMessage = :error"
            expression_attribute_values[":error"] = error_message

        response = self.table.update_item(
            Key={"kbId": kb_id, "documentId": document_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW",
        )
        return response.get("Attributes", {})

    def update_index_lock(
        self, *, kb_id: str, user_id: str, lock_id: str, ttl_seconds: int = 300
    ) -> bool:
        """
        Acquire a lock for updating the KB index.
        Returns True if lock acquired, False otherwise.
        """
        timestamp = int(time.time() * 1000)
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="SET indexLock = :lock, indexLockTime = :time",
                ConditionExpression=(
                    "attribute_not_exists(indexLock) OR "
                    "indexLock = :empty OR "
                    "indexLockTime < :expiry"
                ),
                ExpressionAttributeValues={
                    ":lock": lock_id,
                    ":time": timestamp,
                    ":empty": "",
                    ":expiry": timestamp - (ttl_seconds * 1000),
                },
            )
            return True
        except Exception:
            return False

    def release_index_lock(self, *, kb_id: str, user_id: str, lock_id: str):
        """Release the KB index lock."""
        try:
            self.table.update_item(
                Key={"userId": user_id, "kbId": kb_id},
                UpdateExpression="REMOVE indexLock, indexLockTime",
                ConditionExpression="indexLock = :lock",
                ExpressionAttributeValues={":lock": lock_id},
            )
        except Exception:
            pass

    def delete(self, *, kb_id: str, document_id: str) -> bool:
        try:
            self.table.delete_item(Key={"kbId": kb_id, "documentId": document_id})
            return True
        except Exception as error:
            print(f"Failed to delete document {document_id}: {error}")
            return False
