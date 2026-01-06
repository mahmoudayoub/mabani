import boto3
import os
import json
from urllib.parse import unquote_plus

ecs = boto3.client('ecs')

def handler(event, context):
    print("Received event: " + json.dumps(event))
    
    s3 = boto3.client('s3')
    cluster = os.environ['CLUSTER_NAME']
    task_def = os.environ['TASK_DEF_ARN']
    subnet_id = os.environ['SUBNET_ID']
    security_group = os.environ['SECURITY_GROUP_ID']
    
    for record in event['Records']:
        s3_key = record['s3']['object']['key']
        s3_key = unquote_plus(s3_key)
        
        # Determine mode from path
        mode = 'UNKNOWN'
        if '/parse/' in s3_key: 
            mode = 'PARSE'
        elif '/fill/' in s3_key: 
            mode = 'FILL'
        
        if mode == 'UNKNOWN':
            print(f"Skipping key {s3_key} (not in /parse/ or /fill/)")
            continue
            
        print(f"Starting {mode} task for {s3_key}")
        
        # Run in PUBLIC subnet with Public IP
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
                        'name': 'WorkerContainer',
                        'environment': [
                            {'name': 'S3_KEY', 'value': s3_key},
                            {'name': 'JOB_MODE', 'value': mode},
                            {'name': 'ECS_CLUSTER_NAME', 'value': cluster}
                        ]
                    }
                ]
            }
        )
        
        # Extract task ARN from response
        task_arn = response['tasks'][0]['taskArn']
        print(f"Task started: {task_arn}")

