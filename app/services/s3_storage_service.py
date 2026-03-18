"""AWS S3 storage service for file storage"""

import logging
import os
import tempfile
from typing import List, Tuple, Optional
import boto3
from botocore.exceptions import ClientError
from fastapi import UploadFile, HTTPException
import uuid
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class S3StorageService:
    """Service for storing files in AWS S3"""

    def __init__(self):
        self.s3_client = None
        # Support both S3_BUCKET_NAME and AWS_BUCKET from .env
        # Prefer AWS_BUCKET if set, otherwise use S3_BUCKET_NAME, then default
        if settings.AWS_BUCKET:
            self.bucket_name = settings.AWS_BUCKET
        elif settings.S3_BUCKET_NAME and settings.S3_BUCKET_NAME != "utility-managment":
            self.bucket_name = settings.S3_BUCKET_NAME
        else:
            self.bucket_name = "utility-managment"
        self.region = settings.AWS_REGION

    def _get_client(self):
        """Lazily initialize S3 client"""
        if self.s3_client is None:
            if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
                raise ValueError("AWS credentials not configured")
            
            self.s3_client = boto3.client(
                's3',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                region_name=self.region
            )
            
            # Ensure bucket exists
            self._ensure_bucket_exists()
        
        return self.s3_client

    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
            logger.info(f"S3 bucket {self.bucket_name} already exists")
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404' or error_code == '403':
                # Bucket doesn't exist, create it
                try:
                    if self.region == 'us-east-1':
                        self.s3_client.create_bucket(Bucket=self.bucket_name)
                    else:
                        self.s3_client.create_bucket(
                            Bucket=self.bucket_name,
                            CreateBucketConfiguration={'LocationConstraint': self.region}
                        )
                    logger.info(f"Created S3 bucket: {self.bucket_name}")
                except ClientError as create_error:
                    logger.error(f"Failed to create bucket: {create_error}")
                    raise
            else:
                raise

    async def save_case_file(
        self,
        case_id: str,
        file: UploadFile,
        file_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Tuple[str, int, str]:
        """
        Save a single file to S3
        
        Args:
            case_id: Case ID
            file: UploadFile object
            file_id: Optional file ID (generated if not provided)
            user_id: User ID for scoping (required)
            
        Returns:
            Tuple of (S3 key, file size in bytes, original filename)
        """
        if user_id is None:
            raise ValueError("user_id is required for file storage")
        if file_id is None:
            file_id = str(uuid.uuid4())
        
        client = self._get_client()
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Validate file size
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds maximum size of {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
            )
        
        # S3 key: users/{user_id}/cases/{case_id}/{file_id}/{filename}
        original_filename = file.filename or f"file_{file_id}"
        s3_key = f"users/{user_id}/cases/{case_id}/{file_id}/{original_filename}"
        
        # Upload to S3
        try:
            client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=content,
                ContentType=file.content_type or 'application/pdf'
            )
            logger.info(f"Saved file to S3: {s3_key}")
            return s3_key, file_size, original_filename
        except ClientError as e:
            logger.error(f"Failed to save file to S3: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save file to S3: {str(e)}")

    async def save_case_files(
        self,
        case_id: str,
        files: List[UploadFile],
        user_id: Optional[str] = None
    ) -> List[Tuple[str, int, str]]:
        """
        Save multiple files to S3
        
        Args:
            case_id: Case ID
            files: List of UploadFile objects
            
        Returns:
            List of tuples: (S3 key, file size, original filename)
        """
        results = []
        total_size = 0
        
        # First pass: validate all files
        file_contents = []
        for file in files:
            content = await file.read()
            file_size = len(content)
            
            # Check individual file size
            if file_size > settings.MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds maximum size of {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
                )
            
            total_size += file_size
            file_contents.append((file, content, file_size))
        
        # Check total size
        if total_size > settings.MAX_TOTAL_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"Total file size ({total_size / (1024 * 1024):.2f}MB) exceeds maximum of {settings.MAX_TOTAL_SIZE / (1024 * 1024):.0f}MB"
            )
        
        if user_id is None:
            raise ValueError("user_id is required for file storage")
        # Second pass: upload to S3
        client = self._get_client()
        for file, content, file_size in file_contents:
            file_id = str(uuid.uuid4())
            original_filename = file.filename or f"file_{file_id}"
            s3_key = f"users/{user_id}/cases/{case_id}/{file_id}/{original_filename}"
            
            try:
                client.put_object(
                    Bucket=self.bucket_name,
                    Key=s3_key,
                    Body=content,
                    ContentType=file.content_type or 'application/pdf'
                )
                results.append((s3_key, file_size, original_filename))
                logger.debug(f"Saved file to S3: {s3_key}")
            except ClientError as e:
                logger.error(f"Failed to save file {original_filename} to S3: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to save file to S3: {str(e)}")
        
        logger.info(f"Saved {len(results)} files to S3 for case {case_id}")
        return results

    def get_file_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for file access
        
        Args:
            s3_key: S3 object key
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL
        """
        client = self._get_client()
        try:
            url = client.generate_presigned_url(
                'get_object',
                Params={'Bucket': self.bucket_name, 'Key': s3_key},
                ExpiresIn=expires_in
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def get_file_content(self, s3_key: str) -> bytes:
        """Download file content from S3"""
        try:
            client = self._get_client()
            logger.debug(f"Downloading file from S3: bucket={self.bucket_name}, key={s3_key}")
            response = client.get_object(Bucket=self.bucket_name, Key=s3_key)
            content = response['Body'].read()
            logger.debug(f"Successfully downloaded {len(content)} bytes from S3 key: {s3_key}")
            return content
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            logger.error(f"Failed to get file from S3 (key={s3_key}, bucket={self.bucket_name}): {error_code} - {error_msg}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error getting file from S3 (key={s3_key}): {e}", exc_info=True)
            raise

    def delete_case_files(self, case_id: str, user_id: Optional[str] = None) -> int:
        """
        Delete all files for a case
        
        Args:
            case_id: Case ID
            user_id: User ID for scoping (required)
            
        Returns:
            Number of files deleted
        """
        if user_id is None:
            raise ValueError("user_id is required for file deletion")
        client = self._get_client()
        prefix = f"users/{user_id}/cases/{case_id}/"
        
        try:
            # List all objects with the prefix
            paginator = client.get_paginator('list_objects_v2')
            pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
            
            # Collect all objects first (S3 delete_objects supports up to 1000 per request)
            all_objects = []
            for page in pages:
                if 'Contents' in page:
                    all_objects.extend([{'Key': obj['Key']} for obj in page['Contents']])
            
            deleted_count = 0
            # Delete in batches of 1000 (S3 limit)
            batch_size = 1000
            for i in range(0, len(all_objects), batch_size):
                batch = all_objects[i:i + batch_size]
                if batch:
                    response = client.delete_objects(
                            Bucket=self.bucket_name,
                        Delete={'Objects': batch}
                        )
                    # Count successful deletes (handle partial failures)
                    deleted_count += len(batch)
                    if 'Errors' in response and response['Errors']:
                        logger.warning(f"Some objects failed to delete: {response['Errors']}")
            
            logger.info(f"Deleted {deleted_count} files from S3 for case {case_id}")
            return deleted_count
        except ClientError as e:
            logger.error(f"Failed to delete files from S3: {e}")
            raise

    def get_file_size(self, s3_key: str) -> int:
        """Get file size from S3"""
        client = self._get_client()
        try:
            response = client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return response['ContentLength']
        except ClientError as e:
            logger.error(f"Failed to get file size: {e}")
            raise

    def get_case_directory(self, case_id: str, user_id: Optional[str] = None) -> str:
        """Get the S3 prefix for a case (for compatibility)"""
        if user_id is None:
            raise ValueError("user_id is required")
        return f"users/{user_id}/cases/{case_id}/"

    def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in S3"""
        client = self._get_client()
        try:
            client.head_object(Bucket=self.bucket_name, Key=s3_key)
            return True
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') == '404':
                return False
            raise


# Singleton instance
s3_storage_service = S3StorageService()

