"""SFTP Ingest Worker

Background worker process for SFTP file ingestion.
Can be run as a standalone process or integrated into the main application.
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.services.sftp_ingest_service import sftp_ingest_service
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main entry point for SFTP worker"""
    if not settings.SFTP_ENABLED:
        logger.info("SFTP ingest is disabled. Set SFTP_ENABLED=true to enable.")
        return
    
    if not sftp_ingest_service:
        logger.error("SFTP service not available. Install paramiko: pip install paramiko")
        sys.exit(1)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal, stopping SFTP service...")
        sftp_ingest_service.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        logger.info("Starting SFTP ingest worker...")
        await sftp_ingest_service.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sftp_ingest_service.stop()
    except Exception as e:
        logger.error(f"Fatal error in SFTP worker: {e}", exc_info=True)
        sftp_ingest_service.stop()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

