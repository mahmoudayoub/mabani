import logging
import os
import boto3
from pathlib import Path
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from botocore.exceptions import ClientError
from almabani.config.settings import get_settings

logger = logging.getLogger(__name__)

class StorageService:
    """Abstract storage operations (S3 vs Local)."""
    
    def __init__(self):
        self.settings = get_settings()
        self.type = self.settings.storage_type
        self.bucket = self.settings.s3_bucket_name
        self.region = self.settings.aws_region
        
        self.s3_client = None
        if self.type == 's3':
            if not self.bucket:
                logger.warning("Storage type is S3 but no bucket name provided. Operations may fail.")
            self.s3_client = boto3.client('s3', region_name=self.region)
            logger.info(f"Initialized S3 storage with bucket: {self.bucket}")
        else:
            logger.info("Initialized Local storage")

    def upload_file(self, local_path: Union[str, Path], key: str) -> str:
        """
        Upload a file to storage.
        key: The remote path (e.g. 'uploads/file.xlsx')
        Returns: The key or path used
        """
        local_path = str(local_path)
        
        if self.type == 's3':
            try:
                self.s3_client.upload_file(local_path, self.bucket, key)
                logger.info(f"Uploaded {local_path} to s3://{self.bucket}/{key}")
                return key
            except ClientError as e:
                logger.error(f"S3 Upload error: {e}")
                raise
        else:
            # Local fallback (simulate upload by ensuring it's in the data dir)
            # In local mode, the app usually writes directly to the target folder,
            # so this might just be a no-op or a copy.
            # providing a simple copy implementation for completeness.
            import shutil
            dest_path = self.settings.project_root / 'app' / 'data' / key
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_path, dest_path)
            return str(dest_path)

    def download_file(self, key: str, local_path: Union[str, Path]) -> str:
        """
        Download a file from storage to local path.
        """
        local_path = str(local_path)
        
        if self.type == 's3':
            try:
                # Ensure directory exists
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                self.s3_client.download_file(self.bucket, key, local_path)
                logger.info(f"Downloaded s3://{self.bucket}/{key} to {local_path}")
                return local_path
            except ClientError as e:
                logger.error(f"S3 Download error: {e}")
                raise
        else:
            source_path = self.settings.project_root / 'app' / 'data' / key
            if not source_path.exists():
                raise FileNotFoundError(f"Local file not found: {source_path}")
            
            import shutil
            shutil.copy2(source_path, local_path)
            return local_path

    def list_files(self, prefix: str) -> List[Dict[str, Any]]:
        """
        List files in a 'folder' (prefix).
        Returns list of dicts with name, size, modified.
        """
        files = []
        if self.type == 's3':
            try:
                paginator = self.s3_client.get_paginator('list_objects_v2')
                for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    if 'Contents' in page:
                        for obj in page['Contents']:
                            # Skip the directory itself if it appears
                            if obj['Key'].endswith('/'):
                                continue
                                
                            # Extract relative name from prefix
                            # e.g. prefix='uploads/', key='uploads/foo.xlsx' -> name='foo.xlsx'
                            name = obj['Key'][len(prefix):] if obj['Key'].startswith(prefix) else obj['Key']
                            if name.startswith('/'): name = name[1:]
                            
                            # Skip if empty name (the prefix itself)
                            if not name: continue
                            
                            files.append({
                                'name': name,
                                'key': obj['Key'],
                                'size': obj['Size'],
                                'modified': obj['LastModified'].isoformat()
                            })
                return files
            except ClientError as e:
                logger.error(f"S3 List error: {e}")
                return []
        else:
            folder_path = self.settings.project_root / 'app' / 'data' / prefix
            if not folder_path.exists():
                return []
            
            for f in sorted(folder_path.iterdir(), reverse=True):
                if f.is_file():
                    files.append({
                        'name': f.name,
                        'key': f"{prefix}/{f.name}",
                        'size': f.stat().st_size,
                        'modified': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                    })
            return files

    def get_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generate a presigned URL for downloading."""
        if self.type == 's3':
            try:
                response = self.s3_client.generate_presigned_url('get_object',
                                                            Params={'Bucket': self.bucket,
                                                                    'Key': key},
                                                            ExpiresIn=expiration)
                return response
            except ClientError as e:
                logger.error(f"S3 Presign error: {e}")
                return ""
        else:
            # Local fallback: return relative path handled by Flask
            # This logic assumes the Flask app has a route that can serve these
            return f"/download/{key}"

    def delete_file(self, key: str) -> bool:
        if self.type == 's3':
            try:
                self.s3_client.delete_object(Bucket=self.bucket, Key=key)
                return True
            except ClientError as e:
                logger.error(f"S3 Delete error: {e}")
                return False
        else:
            path = self.settings.project_root / 'app' / 'data' / key
            if path.exists():
                path.unlink()
                return True
            return False

_storage_service = None

def get_storage() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
