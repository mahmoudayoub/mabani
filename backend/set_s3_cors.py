
import boto3
from botocore.exceptions import ClientError

def set_cors():
    s3 = boto3.client('s3')
    bucket_name = 'taskflow-backend-dev-reports'

    cors_configuration = {
        'CORSRules': [{
            'AllowedHeaders': ['*'],
            'AllowedMethods': ['GET', 'HEAD'],
            'AllowedOrigins': ['*'],
            'ExposeHeaders': ['ETag'],
            'MaxAgeSeconds': 3000
        }]
    }

    try:
        s3.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors_configuration)
        print(f"Successfully set CORS for bucket: {bucket_name}")
    except ClientError as e:
        print(f"Error setting CORS: {e}")

if __name__ == '__main__':
    set_cors()
