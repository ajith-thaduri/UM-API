"""Application configuration"""

from typing import List, Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # Allow case-insensitive env var matching
        extra="ignore",  # Ignore extra fields from .env that aren't in the model
    )

    # Application
    APP_NAME: str = "Brightcone UM Shield"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True  # Controlled via .env (DEBUG=True/False)
    SQL_ECHO: bool = False  # Set to True to log SQL statements
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database - PostgreSQL (configured via .env file)
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/dbname"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Storage
    STORAGE_TYPE: str = "s3"  # local, s3, azure
    STORAGE_PATH: str = "./storage"  # Only used for local storage
    MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB per file (matches constants.MAX_FILE_SIZE)
    MAX_TOTAL_SIZE: int = 200 * 1024 * 1024  # 200MB total per case (matches constants.MAX_TOTAL_SIZE)

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "utility-managment"
    # Support AWS_BUCKET as alias (from .env) - will be used if S3_BUCKET_NAME is default
    AWS_BUCKET: str = ""

    # LLM Configuration
    LLM_PROVIDER: str = "openai"  # openai, claude
    LLM_MODEL: str = "gpt-4o"  # Model name (will be overridden by provider-specific settings)
    
    # OpenAI Configuration
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_TEMPERATURE: float = 0.0  # Maximum determinism for clinical extraction
    OPENAI_MAX_TOKENS: int = 12000  # Max output (completion) tokens; override via env
    OPENAI_MAX_TEXT_CHARS: int = 20000  # Maximum characters to send to LLM (input)
    
    # LLM Reproducibility (OpenAI only - Claude doesn't support seed)
    LLM_SEED: int = 42  # Fixed seed for more consistent extraction results
    
    # Claude Configuration
    CLAUDE_API_KEY: str = ""
    # Claude model names (tested with your API key):
    # - "claude-sonnet-4-5-20250929" (✅ Works - Latest Sonnet 4.5, highest quality, recommended)
    # - "claude-sonnet-4-5" (✅ Works - Latest Sonnet 4.5, without date suffix)
    # - "claude-haiku-4-5" (✅ Works - Latest Haiku 4.5, fast and cost-effective)
    # - "claude-3-5-haiku-20241022" (✅ Works - Previous Haiku model)
    # - "claude-3-haiku-20240307" (✅ Works - Older Haiku model)
    # Note: Your API key has access to Claude Sonnet 4.5 (latest and most capable model)!
    CLAUDE_MODEL: str = "claude-sonnet-4-5-20250929"  # Claude Sonnet 4.5 (latest, highest quality)
    CLAUDE_TEMPERATURE: float = 0.0  # Maximum determinism for clinical extraction
    CLAUDE_MAX_TOKENS: int = 12000  # Max output (completion) tokens; override via env
    
    # Gemini Configuration
    GEMINI_API_KEY: str = ""
    
    @field_validator('CLAUDE_API_KEY', mode='before')
    @classmethod
    def clean_claude_api_key(cls, v: str) -> str:
        """Clean API key if it includes duplicate variable name (e.g., 'CLAUDE_API_KEY=sk-ant-...')"""
        if isinstance(v, str):
            # Handle case-insensitive duplicate prefix removal
            v_upper = v.upper()
            if v_upper.startswith('CLAUDE_API_KEY='):
                # Remove the prefix (case-insensitive)
                prefix_len = len('CLAUDE_API_KEY=')
                return v[prefix_len:]
        return v

    # Vector Database - PGVector
    VECTOR_DB_TYPE: str = "pgvector"  # pgvector, pinecone
    PINECONE_API_KEY: str = ""
    PINECONE_ENVIRONMENT: str = "us-east-1"
    # AWS_BUCKET support for legacy/compatibility
    AWS_BUCKET: str = ""
    
    # Embedding Configuration
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIMENSIONS: int = 1536
    
    # Medical Document Guardrail Configuration
    ENABLE_MEDICAL_GUARDRAIL: bool = True  # Enable/disable non-medical document blocking
    GUARDRAIL_STRICT_MODE: bool = True  # If True, reject entire batch if ANY file is non-medical. If False, only reject invalid files.
    
    # Reranking Configuration
    ENABLE_RERANKING: bool = True
    RERANKING_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKING_TOP_K: int = 50  # Initial results before reranking
    
    # Chunking Configuration
    CHUNK_SIZE: int = 800  # Target tokens per chunk
    
    # RAG Adaptive Retrieval Configuration
    ENABLE_ADAPTIVE_TOP_K: bool = True  # Enable document-size-aware top_k
    TOP_K_MIN: int = 20  # Minimum chunks to retrieve
    TOP_K_MAX: int = 100  # Maximum chunks to retrieve
    TOP_K_BASE: int = 30  # Base top_k for small documents
    
    # Extraction Validation Configuration
    ENABLE_EXTRACTION_VALIDATION: bool = True  # Enable validation against source chunks
    EXTRACTION_CONFIDENCE_THRESHOLD: float = 0.5  # Flag items below this threshold
    ENABLE_CRITICAL_FIELD_SCAN: bool = True  # Full document scan for critical fields (admission/discharge dates)
    
    # SFTP Configuration
    SFTP_ENABLED: bool = False  # Enable/disable SFTP ingest
    SFTP_HOST: str = "localhost"
    SFTP_PORT: int = 22
    SFTP_USERNAME: str = ""
    SFTP_PASSWORD: str = ""  # Can use password or key file
    SFTP_KEY_FILE: str = ""  # Path to private key file (alternative to password)
    SFTP_BASE_DIR: str = "/incoming"  # Base directory to watch for files
    SFTP_PROCESSED_DIR: str = "/processed"  # Directory to move processed files
    SFTP_ERROR_DIR: str = "/error"  # Directory to move files with errors
    SFTP_POLL_INTERVAL: int = 60  # Poll interval in seconds
    CHUNK_OVERLAP: int = 100  # Overlap in tokens between chunks (token-based)

    # OCR Configuration
    OCR_ENGINE: str = "tesseract"  # tesseract, azure, textract

    # Security
    SECRET_KEY: str = "your-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days (10080 minutes)

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "https://brightcase-ui.onrender.com",
        "https://um.brightcone.ai",
        "https://www.um.brightcone.ai",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> Any:
        if isinstance(v, str) and not v.startswith("["):
            origins = [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, list):
            origins = [str(i).strip() for i in v if i]
        else:
            return v
            
        return origins

    # Logging
    LOG_LEVEL: str = "INFO"
    
    # Google OAuth Configuration
    GOOGLE_OAUTH_ENABLED: bool = False  # Enable/disable Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Must be the BACKEND callback URL (where Google sends the user after auth).
    # Local: http://localhost:8000/api/v1/auth/oauth/google/callback
    # Production: https://brightcase-api.onrender.com/api/v1/auth/oauth/google/callback
    GOOGLE_REDIRECT_URI: str = ""
    
    # Frontend URL (where backend redirects user after OAuth; must match frontend origin).
    # Local: http://localhost:3000 | Production: https://um.brightcone.ai
    FRONTEND_URL: str = "http://localhost:3000"
    
    # OAuth Encryption (for storing tokens)
    # Generate with: openssl rand -hex 32
    OAUTH_TOKEN_ENCRYPTION_KEY: str = ""

    # Two-tier HIPAA architecture
    # Tier 1: OSS LLM (OpenRouter or self-hosted) — timeline, clinical extraction, contradictions, upload agent (PHI allowed)
    # Tier 2: Claude only — summary generation (no PHI; dates shifted per case)
    TIER1_LLM_PROVIDER: str = ""  # "openrouter" to use OpenRouter for Tier 1
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_MODEL: str = "meta-llama/llama-3.1-70b-instruct"  # or e.g. "anthropic/claude-3-haiku" for testing
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENROUTER_TEMPERATURE: float = 0.1
    OPENROUTER_MAX_TOKENS: int = 12000
    
    # Tier 2 summary: always Claude; payload is de-identified and date-shifted before send
    TIER2_SUMMARY_PROVIDER: str = "claude"  # Always Claude
    TIER2_SUMMARY_DEIDENTIFY: bool = True  # Apply date shift and PHI strip before sending to Claude
    
    # Presidio De-Identification Configuration
    PRESIDIO_LANGUAGE: str = "en"
    PRESIDIO_NER_ENGINE: str = "transformers"  # "spacy" or "transformers"
    PRESIDIO_NER_MODEL: str = "en_core_web_lg"  # spaCy model (used when engine=spacy)
    PRESIDIO_TRANSFORMER_MODEL: str = "StanfordAIMI/stanford-deidentifier-base"  # HuggingFace model (used when engine=transformers). Default: Stanford AIMI PubMedBERT-based medical de-identifier
    PRESIDIO_ENTITIES: List[str] = [
        "PERSON",
        "PHONE_NUMBER",
        "US_SSN",
        "EMAIL_ADDRESS",
        "LOCATION",
        "ORGANIZATION",
    ]
    PRESIDIO_FREE_TEXT_THRESHOLD: float = 0.9  # Required by compliance: only redact if confidence >= 0.9
    PRESIDIO_PREFLIGHT_THRESHOLD: float = 0.9  # Ultra-sensitive for pre-flight validation
    
    # Token Format (UUID12 = 48 bits, ~281 trillion combinations)
    # This minimizes collision risk even at multi-million entity scale
    TOKEN_UUID_LENGTH: int = 12  # Characters from UUID (8=32bit, 12=48bit, 16=64bit)
    
    # Date Shifting
    DATE_SHIFT_MIN_DAYS: int = 0
    DATE_SHIFT_MAX_DAYS: int = 30
    
    # Privacy Vault (stores token maps and date shift offsets)
    PRIVACY_VAULT_RETENTION_DAYS: int = 90  # Vault entries auto-expire after this period
    
    # Safety Controls
    ENABLE_PREFLIGHT_VALIDATION: bool = True  # Fail-closed: block if PHI detected before Tier 2
    TREAT_CASE_NUMBER_AS_PHI: bool = True  # Default: tokenize case numbers (can override for internal IDs)
    ENABLE_TWO_TIER_ARCHITECTURE: bool = True  # Feature flag for gradual rollout


settings = Settings()

