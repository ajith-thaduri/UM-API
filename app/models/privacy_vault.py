"""Privacy Vault model for de-identification token storage and date shift tracking.

This model stores the re-identification mappings for de-identified data sent to Tier 2.
Each vault entry contains:
- Token map: UUID tokens → original PHI values (1:1 mapping)
- Date shift offset: Random offset applied to all dates in the case
- Shifted field paths: Structure-aware tracking for precise date reversal

Vault entries expire after PRIVACY_VAULT_RETENTION_DAYS (default: 90 days).
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
import uuid

from app.db.session import Base
from app.core.config import settings


class PrivacyVault(Base):
    """Privacy Vault for HIPAA-compliant de-identification tracking"""

    __tablename__ = "privacy_vault"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(
        String, ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Date shifting: random offset in [0, 30] days
    date_shift_days = Column(Integer, nullable=False)

    # Token map: { "[[PERSON::a94f2c3b12ef]]": "John Doe", ... }
    # CRITICAL: This is 1:1 mapping, every entity instance gets a unique token
    # Format: [[TYPE::uuid12]] (48 bits, ~281 trillion combinations)
    token_map = Column(JSONB, nullable=False, default=dict)

    # Shifted date field paths (for structure-aware reversal)
    # [{"path": "timeline[0].date", "original": "2024-01-15", "shifted": "2024-02-01"}, ...]
    shifted_fields = Column(JSONB, nullable=True, default=list)

    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_privacy_vault_case", "case_id"),
        Index("idx_privacy_vault_user", "user_id"),
        Index("idx_privacy_vault_expires", "expires_at"),
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Set expiration date based on retention policy
        if not self.expires_at:
            retention_days = getattr(settings, "PRIVACY_VAULT_RETENTION_DAYS", 90)
            self.expires_at = datetime.utcnow() + timedelta(days=retention_days)

    def __repr__(self):
        return f"<PrivacyVault case_id={self.case_id} tokens={len(self.token_map)} expires={self.expires_at}>"
