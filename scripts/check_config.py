
import boto3
import json
import os

TABLE_NAME = "taskflow-backend-dev-reports"
AWS_PROFILE = "mia40"
AWS_REGION = "eu-west-1"

def check_config():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table(TABLE_NAME)
    
    print(f"Fetching CONFIG/PROJECTS from {TABLE_NAME}...")
    
    try:
        response = table.get_item(
            Key={
                "PK": "CONFIG",
                "SK": "PROJECTS"
            }
        )
        item = response.get("Item")
        if item:
            print("Found Item:")
            print(json.dumps(item.get("values", "NO_VALUES"), indent=2, default=str))
        else:
            print("Item NOT FOUND (will use defaults).")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_config()
