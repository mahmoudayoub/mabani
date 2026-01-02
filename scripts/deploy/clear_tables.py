import boto3
import sys

def clear_table(table_name, profile="mia40", region="eu-west-1"):
    print(f"Clearing table: {table_name}")
    session = boto3.Session(profile_name=profile, region_name=region)
    dynamodb = session.resource('dynamodb')
    table = dynamodb.Table(table_name)

    try:
        # Scan and delete is inefficient but sufficient for dev/cleanup
        scan = table.scan()
        with table.batch_writer() as batch:
            for each in scan['Items']:
                # We need the primary keys to delete
                # Assuming simple keys or standard specialized keys for these tables
                # But batch_writer.delete_item needs the Key dict
                
                # Fetch key schema to build key dict
                key_names = [k['AttributeName'] for k in table.key_schema]
                key_dict = {k: each[k] for k in key_names}
                
                batch.delete_item(Key=key_dict)
                
        print(f"Successfully cleared {table_name}")
    except Exception as e:
        print(f"Error clearing {table_name}: {e}")

if __name__ == "__main__":
    tables = [
        "taskflow-backend-dev-knowledge-bases",
        "taskflow-backend-dev-documents",
        "taskflow-backend-dev-reports",
        "taskflow-backend-dev-conversations"
    ]
    
    for table in tables:
        clear_table(table)
