"""Local file system storage service"""

import logging
import os
import shutil
from typing import List, Tuple, Optional
from pathlib import Path
from fastapi import UploadFile, HTTPException
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalStorageService:
    """Service for storing files on local file system"""

    def __init__(self):
        self.storage_path = Path(settings.STORAGE_PATH)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Local storage initialized at: {self.storage_path}")

    def _get_file_path(self, case_id: str, file_id: str, filename: str, user_id: Optional[str] = None) -> Path:
        """Get the full file path for a case file"""
        if user_id is None:
            raise ValueError("user_id is required for file storage")
        # Path structure: storage/users/{user_id}/cases/{case_id}/{file_id}/{filename}
        file_path = self.storage_path / "users" / user_id / "cases" / case_id / file_id / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        return file_path

    def _get_s3_key_from_path(self, file_path: Path) -> str:
        """Convert local file path to S3-key-like string for compatibility"""
        # Get relative path from storage_path
        relative_path = file_path.relative_to(self.storage_path)
        # Convert to forward slashes (S3 key format)
        return str(relative_path).replace("\\", "/")

    async def save_case_file(
        self,
        case_id: str,
        file: UploadFile,
        file_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Tuple[str, int, str]:
        """
        Save a single file to local storage
        
        Args:
            case_id: Case ID
            file: UploadFile object
            file_id: Optional file ID (generated if not provided)
            user_id: User ID for scoping (required)
            
        Returns:
            Tuple of (file path as S3-key-like string, file size in bytes, original filename)
        """
        if user_id is None:
            raise ValueError("user_id is required for file storage")
        if file_id is None:
            file_id = str(uuid.uuid4())
        
        # Read file content
        content = await file.read()
        file_size = len(content)
        
        # Validate file size
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File {file.filename} exceeds maximum size of {settings.MAX_FILE_SIZE / (1024 * 1024):.0f}MB"
            )
        
        # Save to local file system
        original_filename = file.filename or f"file_{file_id}"
        file_path = self._get_file_path(case_id, file_id, original_filename, user_id)
        
        try:
            with open(file_path, 'wb') as f:
                f.write(content)
            logger.info(f"Saved file to local storage: {file_path}")
            # Return S3-key-like string for compatibility
            s3_key = self._get_s3_key_from_path(file_path)
            return s3_key, file_size, original_filename
        except Exception as e:
            logger.error(f"Failed to save file to local storage: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    async def save_case_files(
        self,
        case_id: str,
        files: List[UploadFile],
        user_id: Optional[str] = None
    ) -> List[Tuple[str, int, str]]:
        """
        Save multiple files to local storage
        
        Args:
            case_id: Case ID
            files: List of UploadFile objects
            user_id: User ID for scoping (required)
            
        Returns:
            List of tuples: (file path as S3-key-like string, file size, original filename)
        """
        if user_id is None:
            raise ValueError("user_id is required for file storage")
        
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
        
        # Second pass: save to local storage
        for file, content, file_size in file_contents:
            file_id = str(uuid.uuid4())
            original_filename = file.filename or f"file_{file_id}"
            file_path = self._get_file_path(case_id, file_id, original_filename, user_id)
            
            try:
                with open(file_path, 'wb') as f:
                    f.write(content)
                s3_key = self._get_s3_key_from_path(file_path)
                results.append((s3_key, file_size, original_filename))
                logger.debug(f"Saved file to local storage: {file_path}")
            except Exception as e:
                logger.error(f"Failed to save file {original_filename}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")
        
        logger.info(f"Saved {len(results)} files to local storage for case {case_id}")
        return results

    def get_file_url(self, s3_key: str, expires_in: int = 3600) -> str:
        """
        Generate a file URL for local storage (returns file path)
        
        Args:
            s3_key: File path (S3-key-like string)
            expires_in: Not used for local storage (kept for compatibility)
            
        Returns:
            File path as string
        """
        file_path = self.storage_path / s3_key
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {s3_key}")
        return str(file_path.absolute())

    def get_file_content(self, s3_key: str) -> bytes:
        """Download file content from local storage"""
        try:
            file_path = self.storage_path / s3_key
            logger.debug(f"Reading file from local storage: {file_path}")
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {s3_key}")
            with open(file_path, 'rb') as f:
                content = f.read()
            logger.debug(f"Successfully read {len(content)} bytes from: {s3_key}")
            return content
        except FileNotFoundError:
            logger.error(f"File not found: {s3_key}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading file ({s3_key}): {e}", exc_info=True)
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
        
        case_dir = self.storage_path / "users" / user_id / "cases" / case_id
        if not case_dir.exists():
            logger.warning(f"Case directory does not exist: {case_dir}")
            return 0
        
        try:
            # Count files before deletion
            deleted_count = sum(1 for _ in case_dir.rglob('*') if _.is_file())
            
            # Delete the entire case directory
            shutil.rmtree(case_dir)
            logger.info(f"Deleted {deleted_count} files from local storage for case {case_id}")
            return deleted_count
        except Exception as e:
            logger.error(f"Failed to delete files from local storage: {e}")
            raise

    def get_file_size(self, s3_key: str) -> int:
        """Get file size from local storage"""
        try:
            file_path = self.storage_path / s3_key
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {s3_key}")
            return file_path.stat().st_size
        except Exception as e:
            logger.error(f"Failed to get file size: {e}")
            raise

    def get_case_directory(self, case_id: str, user_id: Optional[str] = None) -> str:
        """Get the directory path for a case (for compatibility)"""
        if user_id is None:
            raise ValueError("user_id is required")
        return f"users/{user_id}/cases/{case_id}/"

    def file_exists(self, s3_key: str) -> bool:
        """Check if file exists in local storage"""
        file_path = self.storage_path / s3_key
        return file_path.exists() and file_path.is_file()


# Singleton instance
local_storage_service = LocalStorageService()

