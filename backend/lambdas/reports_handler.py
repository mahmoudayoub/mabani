
import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Dict, Any, List
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

def _create_response(status_code: int, body: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Credentials": True,
        },
        "body": json.dumps(body, cls=DecimalEncoder)
    }

def list_reports(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    List safety reports.
    Supports filtering by severity, date, etc. in the future.
    For now, returns the most recent 50 terms.
    """
    try:
        dynamodb = boto3.resource("dynamodb")
        table_name = os.environ.get("REPORTS_TABLE")
        if not table_name:
             return _create_response(500, {"error": "Server configuration error: REPORTS_TABLE not set"})

        table = dynamodb.Table(table_name)

        # Ideally, use GSI for sorted access.
        # GSI1PK = "REPORT" (need to ensure write side does this)
        # GSI1SK = timestamp
        
        # Check if we can query GSI1
        # If GSI is not populated yet for old items, Scan might be needed as fallback or primary if low volume.
        
        # Strategies:
        # 1. Query GSI1 if available.
        # 2. Scan if not.
        
        # Let's try Query first, assuming we update the writer.
        # Actually, for robustness during dev where data might be mixed:
        # We will use Scan with a Limit and Filter for SK="METADATA" or just "PK" starts with "REPORT#"
        
        # Scanning is safer for "list" until we are sure about GSI.
        # Try Query on GSI1 (status = 'closed' or 'open')
        # Assuming the PK for GSI is status and SK is completedAt/timestamp
        # If GSI doesn't exist, this will fallback to Scan safely.
        try:
            response = table.query(
                IndexName="StatusIndex", # Assuming this exists from original design
                KeyConditionExpression=Key('status').eq('closed'),
                ScanIndexForward=False, # Descending by date
                Limit=100
            )
            items = response.get("Items", [])
            
            # If nothing returned, it might be an open report or index missing
            if not items:
                response = table.scan(
                    FilterExpression=Attr("SK").eq("METADATA"),
                    Limit=150
                )
                items = response.get("Items", [])
                items.sort(key=lambda x: x.get("completedAt", x.get("timestamp", "")), reverse=True)
                
        except Exception as e:
            print(f"GSI Query failed, falling back to Scan: {e}")
            response = table.scan(
                FilterExpression=Attr("SK").eq("METADATA"),
                Limit=150
            )
            items = response.get("Items", [])
            items.sort(key=lambda x: x.get("completedAt", x.get("timestamp", "")), reverse=True)
            
        # Return only what we need to avoid massive payload transfer
        return _create_response(200, items)

    except Exception as e:
        print(f"Error listing reports: {e}")
        return _create_response(500, {"error": str(e)})

def get_report(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Get a specific report by ID.
    """
    try:
        report_id = event.get("pathParameters", {}).get("id")
        if not report_id:
             return _create_response(400, {"error": "Missing report ID"})

        dynamodb = boto3.resource("dynamodb")
        table_name = os.environ.get("REPORTS_TABLE")
        table = dynamodb.Table(table_name)
        
        # PK = REPORT#{id}, SK = METADATA
        response = table.get_item(Key={"PK": f"REPORT#{report_id}", "SK": "METADATA"})
        item = response.get("Item")
        
        if not item:
            return _create_response(404, {"error": "Report not found"})
            
        return _create_response(200, item)

    except Exception as e:
        print(f"Error getting report: {e}")
        return _create_response(500, {"error": str(e)})
