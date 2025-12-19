
import boto3
import os

# Configuration
TABLE_NAME = "taskflow-backend-dev-reports"
REGION = "eu-west-1"

def cleanup_logs():
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)
    
    print(f"Scanning table {TABLE_NAME} for logs without 'reportNumber'...")
    
    # Scan for items where reportNumber is missing
    # We will scan all items and filter in python to be safe, 
    # or use FilterExpression attribute_not_exists(reportNumber)
    
    response = table.scan()
    items = response.get("Items", [])
    
    deleted_count = 0
    
    for item in items:
        # Check if it's a report metadata item
        if item.get("SK") == "METADATA":
            # Check if reportNumber is missing or (if it's a string/number) is None
            if "reportNumber" not in item:
                print(f"Deleting item PK: {item['PK']} (Missing reportNumber)")
                table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                deleted_count += 1
            elif item["reportNumber"] is None: 
                print(f"Deleting item PK: {item['PK']} (Null reportNumber)")
                table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                deleted_count += 1
                
    print(f"Cleanup complete. Deleted {deleted_count} items.")

if __name__ == "__main__":
    cleanup_logs()
