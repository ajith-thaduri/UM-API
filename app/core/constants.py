"""Application constants"""

# File size limits (in bytes)
MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB per file
MAX_TOTAL_SIZE: int = 200 * 1024 * 1024  # 200MB total per case

# Timeout values (in seconds)
DATABASE_CONNECT_TIMEOUT: int = 10
DEFAULT_REQUEST_TIMEOUT: int = 30
LLM_REQUEST_TIMEOUT: int = 120  # LLM calls can take longer

# Default schema name
DEFAULT_POSTGRES_SCHEMA: str = "public"

# Pagination defaults
DEFAULT_PAGE_SIZE: int = 20
MAX_PAGE_SIZE: int = 100

# Cache TTL (in seconds)
DEFAULT_CACHE_TTL: int = 300  # 5 minutes

# Timeline Processing Constants
MAX_DESCRIPTION_LENGTH: int = 500  # Maximum event description length
MAX_HISTORY_MESSAGES: int = 10  # Maximum conversation history messages
DEFAULT_DATE_FORMAT: str = "%m/%d/%Y"  # Standard date format for display
EPOCH_DATE: str = "01/01/1970"  # Epoch date for sorting fallback

