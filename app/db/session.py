"""Database session and connection management"""

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.exc import OperationalError, DisconnectionError
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


def ensure_schema_exists(engine):
    """Check if schema exists, create if not (for PostgreSQL)"""
    if not settings.DATABASE_URL.startswith("postgresql"):
        return  # Only for PostgreSQL
    
    try:
        # Extract schema name from URL or use default 'public'
        schema_name = "public"  # Default PostgreSQL schema
        
        # Check if schema exists using parameterized query to prevent SQL injection
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT schema_name FROM information_schema.schemata WHERE schema_name = :schema_name"),
                {"schema_name": schema_name}
            )
            exists = result.fetchone() is not None
            
            if not exists:
                logger.info(f"Creating schema: {schema_name}")
                conn.execute(text("CREATE SCHEMA IF NOT EXISTS :schema_name").bindparams(schema_name=schema_name))
                conn.commit()
                logger.info(f"Schema {schema_name} created successfully")
            else:
                logger.info(f"Schema {schema_name} already exists")
    except Exception as e:
        logger.warning(f"Could not check/create schema: {e}")


# Create database engine with robust connection handling
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,  # Verify connections before using (pings before each use)
    pool_recycle=1800,  # Recycle connections after 30 min (prevents stale connections)
    pool_timeout=30,  # Wait up to 30s for a connection from pool
    echo=settings.SQL_ECHO,  # Controlled via .env (SQL_ECHO=True/False)
    # PostgreSQL-specific optimizations
    connect_args={
        "connect_timeout": 30,  # Increased from 10 to 30
        "keepalives": 1,  # Enable TCP keepalives
        "keepalives_idle": 30,  # Start keepalive after 30s idle
        "keepalives_interval": 10,  # Send keepalive every 10s
        "keepalives_count": 5,  # Close after 5 failed keepalives
        "options": "-c timezone=utc -c statement_timeout=180000"  # 3 min statement timeout
    } if settings.DATABASE_URL.startswith("postgresql") else {}
)

# Ensure schema exists before creating tables
ensure_schema_exists(engine)

# Add event listener to handle connection errors and set PostgreSQL parameters
@event.listens_for(engine, "connect")
def set_postgres_pragmas(dbapi_conn, connection_record):
    """Set PostgreSQL connection parameters to prevent connection issues"""
    if settings.DATABASE_URL.startswith("postgresql"):
        try:
            # Set timeouts to handle long-running operations (large document processing)
            with dbapi_conn.cursor() as cursor:
                cursor.execute("SET statement_timeout = '300s'")  # 5 min instead of 30s
                cursor.execute("SET idle_in_transaction_session_timeout = '10min'")
        except Exception as e:
            logger.warning(f"Could not set PostgreSQL connection parameters: {e}")

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for getting database session.
    pool_pre_ping=True ensures connections are tested before use,
    automatically replacing stale connections.
    """
    db = SessionLocal()
    try:
        yield db
    except (OperationalError, DisconnectionError) as e:
        logger.error(f"Database connection error: {e}. Rolling back transaction.")
        db.rollback()
        raise
    except Exception as e:
        logger.error(f"Database error: {e}. Rolling back transaction.")
        db.rollback()
        raise
    finally:
        db.close()

