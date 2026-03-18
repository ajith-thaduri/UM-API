"""SFTP Ingest Service

Service for monitoring SFTP directories and processing uploaded files.
Runs as a background service to watch for new files and create cases.
"""

import os
import logging
import shutil
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import uuid
import asyncio
from io import BytesIO

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False
    logging.warning("paramiko not installed. SFTP functionality will be unavailable.")

from app.core.config import settings

logger = logging.getLogger(__name__)


class SFTPIngestService:
    """Service for SFTP file ingestion"""
    
    def __init__(self):
        if not PARAMIKO_AVAILABLE:
            raise ImportError("paramiko package is required for SFTP functionality. Install with: pip install paramiko")
        
        self.enabled = settings.SFTP_ENABLED
        self.host = settings.SFTP_HOST
        self.port = settings.SFTP_PORT
        self.username = settings.SFTP_USERNAME
        self.password = settings.SFTP_PASSWORD
        self.key_file = settings.SFTP_KEY_FILE
        self.base_dir = settings.SFTP_BASE_DIR
        self.processed_dir = settings.SFTP_PROCESSED_DIR
        self.error_dir = settings.SFTP_ERROR_DIR
        self.poll_interval = settings.SFTP_POLL_INTERVAL
        
        self._running = False
        self._client: Optional[paramiko.SSHClient] = None
        self._sftp: Optional[paramiko.SFTPClient] = None
        self._processed_files: set = set()  # Track processed files to avoid duplicates
    
    def _connect(self) -> bool:
        """Establish SFTP connection"""
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Use key file if provided, otherwise use password
            if self.key_file and os.path.exists(self.key_file):
                self._client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    key_filename=self.key_file,
                    timeout=30
                )
            else:
                if not self.password:
                    logger.error("SFTP password or key file required")
                    return False
                self._client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    timeout=30
                )
            
            self._sftp = self._client.open_sftp()
            logger.info(f"Connected to SFTP server {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to SFTP server: {e}")
            return False
    
    def _disconnect(self):
        """Close SFTP connection"""
        try:
            if self._sftp:
                self._sftp.close()
            if self._client:
                self._client.close()
            logger.debug("Disconnected from SFTP server")
        except Exception as e:
            logger.warning(f"Error disconnecting from SFTP: {e}")
        finally:
            self._sftp = None
            self._client = None
    
    def _ensure_directories(self):
        """Ensure required directories exist on SFTP server"""
        if not self._sftp:
            return
        
        try:
            # Create directories if they don't exist
            for dir_path in [self.base_dir, self.processed_dir, self.error_dir]:
                try:
                    self._sftp.chdir(dir_path)
                except IOError:
                    # Directory doesn't exist, create it
                    try:
                        self._sftp.mkdir(dir_path)
                        logger.info(f"Created SFTP directory: {dir_path}")
                    except Exception as e:
                        logger.warning(f"Failed to create directory {dir_path}: {e}")
        except Exception as e:
            logger.warning(f"Error ensuring directories exist: {e}")
    
    def _list_files(self) -> List[Dict]:
        """List PDF files in the base directory"""
        if not self._sftp:
            return []
        
        files = []
        try:
            self._sftp.chdir(self.base_dir)
            file_list = self._sftp.listdir_attr('.')
            
            for attr in file_list:
                # Only process PDF files
                if attr.filename.lower().endswith('.pdf') and not attr.filename.startswith('.'):
                    file_key = f"{attr.filename}_{attr.st_size}_{attr.st_mtime}"
                    # Skip if already processed
                    if file_key not in self._processed_files:
                        files.append({
                            "filename": attr.filename,
                            "size": attr.st_size,
                            "mtime": attr.st_mtime,
                            "key": file_key
                        })
        except Exception as e:
            logger.error(f"Error listing files from SFTP: {e}")
        
        return files
    
    def _download_file(self, filename: str) -> Optional[bytes]:
        """Download file from SFTP server"""
        if not self._sftp:
            return None
        
        try:
            file_path = f"{self.base_dir}/{filename}"
            with BytesIO() as buffer:
                self._sftp.getfo(file_path, buffer)
                return buffer.getvalue()
        except Exception as e:
            logger.error(f"Error downloading file {filename} from SFTP: {e}")
            return None
    
    def _move_file(self, filename: str, destination_dir: str) -> bool:
        """Move file to processed or error directory"""
        if not self._sftp:
            return False
        
        try:
            source_path = f"{self.base_dir}/{filename}"
            dest_path = f"{destination_dir}/{filename}"
            
            # Ensure destination directory exists
            try:
                self._sftp.chdir(destination_dir)
            except IOError:
                self._sftp.mkdir(destination_dir)
            
            # Move file
            self._sftp.rename(source_path, dest_path)
            logger.info(f"Moved file {filename} to {destination_dir}")
            return True
        except Exception as e:
            logger.error(f"Error moving file {filename} to {destination_dir}: {e}")
            return False
    
    async def _process_file(self, filename: str, file_data: bytes) -> bool:
        """
        Process a downloaded file by creating a case
        
        This method should integrate with the case upload logic.
        For now, it's a placeholder that should be implemented based on
        the specific requirements for auto-creating cases from SFTP files.
        """
        try:
            # TODO: Implement case creation logic
            # This should:
            # 1. Extract metadata from filename or directory structure
            # 2. Create a case using the case creation service
            # 3. Upload the file(s) to the case
            
            logger.info(f"Processing SFTP file: {filename} ({len(file_data)} bytes)")
            
            # Placeholder - actual implementation depends on requirements
            # Example structure:
            # - Parse filename for case number, patient ID, etc.
            # - Create case via case_repository
            # - Upload file via storage_service
            # - Trigger processing via case_processor
            
            return True
        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}", exc_info=True)
            return False
    
    async def _poll_once(self):
        """Perform one polling cycle"""
        if not self._client or not self._sftp:
            if not self._connect():
                return
            self._ensure_directories()
        
        try:
            # List new files
            files = self._list_files()
            
            for file_info in files:
                filename = file_info["filename"]
                file_key = file_info["key"]
                
                logger.info(f"Found new SFTP file: {filename}")
                
                # Download file
                file_data = self._download_file(filename)
                if not file_data:
                    logger.warning(f"Failed to download {filename}, skipping")
                    continue
                
                # Process file
                success = await self._process_file(filename, file_data)
                
                # Move file to appropriate directory
                if success:
                    self._move_file(filename, self.processed_dir)
                    self._processed_files.add(file_key)
                else:
                    self._move_file(filename, self.error_dir)
                    
        except Exception as e:
            logger.error(f"Error in SFTP polling cycle: {e}", exc_info=True)
            # Reconnect on error
            self._disconnect()
    
    async def start(self):
        """Start the SFTP ingest service"""
        if not self.enabled:
            logger.info("SFTP ingest is disabled in configuration")
            return
        
        if not PARAMIKO_AVAILABLE:
            logger.error("paramiko not available, cannot start SFTP service")
            return
        
        logger.info(f"Starting SFTP ingest service for {self.host}:{self.port}")
        self._running = True
        
        while self._running:
            try:
                await self._poll_once()
            except Exception as e:
                logger.error(f"Unexpected error in SFTP service: {e}", exc_info=True)
            
            # Wait before next poll
            await asyncio.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the SFTP ingest service"""
        logger.info("Stopping SFTP ingest service")
        self._running = False
        self._disconnect()


# Singleton instance
sftp_ingest_service = SFTPIngestService() if PARAMIKO_AVAILABLE else None

