import boto3
import sys

def empty_bucket(bucket_name, profile="mia40", region="eu-west-1"):
    print(f"Emptying bucket: {bucket_name}")
    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.resource('s3')
    bucket = s3.Bucket(bucket_name)

    try:
        bucket.object_versions.delete()
        print(f"Successfully emptied {bucket_name}")
    except Exception as e:
        print(f"Error emptying {bucket_name}: {e}")

if __name__ == "__main__":
    buckets = [
        "taskflow-backend-dev-reports",
        "taskflow-backend-dev-kb",
        "taskflow-backend-dev-serverlessdeploymentbucket-jcboksmgyjz6"
    ]
    
    for bucket in buckets:
        empty_bucket(bucket)
