import boto3
import os
import json
from urllib.parse import unquote_plus

ecs = boto3.client('ecs')

def handler(event, context):
    """
    Lambda trigger for Price Code pipeline.
    
    Triggers on:
    - input/pricecode/index/   → INDEX mode (index price codes)
    - input/pricecode/allocate/ → ALLOCATE mode (allocate to BOQ)
    """
    print("Price Code Trigger received event: " + json.dumps(event))
    
    cluster = os.environ['CLUSTER_NAME']
    task_def = os.environ['TASK_DEF_ARN']
    subnet_id = os.environ['SUBNET_ID']
    security_group = os.environ['SECURITY_GROUP_ID']
    
    for record in event['Records']:
        s3_key = record['s3']['object']['key']
        s3_key = unquote_plus(s3_key)
        
        # Determine mode from path
        mode = 'UNKNOWN'
        if '/pricecode/index/' in s3_key:
            mode = 'INDEX'
        elif '/pricecode/allocate/' in s3_key:
            mode = 'ALLOCATE'
        
        if mode == 'UNKNOWN':
            print(f"Skipping key {s3_key} (not in /pricecode/index/ or /pricecode/allocate/)")
            continue
        
        print(f"Starting Price Code {mode} task for {s3_key}")
        
        response = ecs.run_task(
            cluster=cluster,
            taskDefinition=task_def,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': [subnet_id],
                    'securityGroups': [security_group],
                    'assignPublicIp': 'ENABLED'
                }
            },
            overrides={
                'containerOverrides': [
                    {
                        'name': 'PriceCodeWorkerContainer',
                        'environment': [
                            {'name': 'S3_KEY', 'value': s3_key},
                            {'name': 'JOB_MODE', 'value': mode},
                            {'name': 'ECS_CLUSTER_NAME', 'value': cluster}
                        ]
                    }
                ]
            }
        )
        
        task_arn = response['tasks'][0]['taskArn']
        print(f"Price Code task started: {task_arn}")
