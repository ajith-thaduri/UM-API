"""Usage tracking service for LLM token usage and cost calculation"""

import uuid
import logging
from datetime import datetime
from typing import Dict, Optional, Any, List
from decimal import Decimal
from sqlalchemy.orm import Session

from app.models.usage_metrics import UsageMetrics
from app.repositories.usage_metrics_repository import UsageMetricsRepository

logger = logging.getLogger(__name__)


# Pricing per 1M tokens (as of 2024-2025)
# These should be updated periodically based on provider pricing changes
LLM_PRICING = {
    "openai": {
        # Reference: OpenAI published API rates (rounded to $/1M tokens)
        # https://openai.com/api/pricing
        "gpt-4o": {
            "prompt": 5.00,    # $5.00 per 1M input tokens
            "completion": 15.00,  # $15.00 per 1M output tokens
        },
        "gpt-4o-mini": {
            "prompt": 0.15,    # $0.15 per 1M input tokens
            "completion": 0.60,   # $0.60 per 1M output tokens
        },
        "gpt-4-turbo": {
            "prompt": 10.00,
            "completion": 30.00,
        },
        "gpt-3.5-turbo": {
            "prompt": 0.50,
            "completion": 1.50,
        },
    },
    "claude": {
        # Reference: Anthropic API pricing (Claude 3.5/3.x family)
        # https://www.anthropic.com/pricing
        "claude-3-5-sonnet": {
            "prompt": 3.00,   # $3.00 per 1M input tokens
            "completion": 15.00,  # $15.00 per 1M output tokens
        },
        # Claude Sonnet 4.5 models
        "claude-sonnet-4-5-20250929": {
            "prompt": 3.00,
            "completion": 15.00,
        },
        "claude-sonnet-4-5": {
            "prompt": 3.00,
            "completion": 15.00,
        },
        # Claude Haiku 4.5 models
        "claude-haiku-4-5": {
            "prompt": 1.00,   # $1.00 per 1M input tokens
            "completion": 5.00,   # $5.00 per 1M output tokens
        },
        "claude-3-5-haiku": {
            "prompt": 1.00,   # $1.00 per 1M input tokens (Haiku 4.5)
            "completion": 5.00,   # $5.00 per 1M output tokens
        },
        "claude-3-5-haiku-20241022": {
            "prompt": 1.00,   # $1.00 per 1M input tokens (Haiku 4.5)
            "completion": 5.00,   # $5.00 per 1M output tokens
        },
        # Claude Haiku 3.5 model
        "claude-3-haiku-20240307": {
            "prompt": 0.80,   # $0.80 per 1M input tokens (Haiku 3.5)
            "completion": 4.00,   # $4.00 per 1M output tokens
        },
    },
}


class UsageTrackingService:
    """Service for tracking LLM usage and calculating costs"""

    def __init__(self):
        self.repository = UsageMetricsRepository()

    def calculate_cost(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Optional[Decimal]:
        """
        Calculate estimated cost for LLM usage

        Args:
            provider: LLM provider (openai/claude)
            model: Model name
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            Estimated cost in USD or None if pricing not available
        """
        try:
            pricing = LLM_PRICING.get(provider.lower(), {}).get(model.lower())
            if not pricing:
                # Try to find pricing for similar model (fallback)
                logger.debug(f"No pricing found for {provider}/{model}, using default")
                return None
            
            # Calculate cost: (tokens / 1M) * price_per_1M
            prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
            completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
            total_cost = prompt_cost + completion_cost
            
            return Decimal(str(total_cost)).quantize(Decimal('0.000001'))
        except Exception as e:
            logger.warning(f"Error calculating cost for {provider}/{model}: {e}")
            return None

    def track_llm_usage(
        self,
        db: Session,
        user_id: str,
        provider: str,
        model: str,
        operation_type: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        case_id: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        calculate_cost: bool = True
    ) -> UsageMetrics:
        """
        Track LLM usage and store in database

        Args:
            db: Database session
            user_id: User ID
            provider: LLM provider (openai/claude)
            model: Model name
            operation_type: Type of operation (extraction/timeline/summary/rag/etc.)
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens
            total_tokens: Total tokens
            case_id: Optional case ID
            metadata: Optional additional metadata
            calculate_cost: Whether to calculate and store cost

        Returns:
            Created UsageMetrics instance
        """
        # Calculate cost if enabled
        estimated_cost = None
        if calculate_cost:
            estimated_cost = self.calculate_cost(provider, model, prompt_tokens, completion_tokens)

        # Create usage metrics record
        usage_metric = UsageMetrics(
            id=str(uuid.uuid4()),
            user_id=user_id,
            case_id=case_id,
            provider=provider.lower(),
            model=model,
            operation_type=operation_type,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost,
            request_timestamp=datetime.utcnow(),
            extra_metadata=extra_metadata
        )

        try:
            db.add(usage_metric)
            db.commit()
            db.refresh(usage_metric)
            logger.debug(f"Tracked usage: {provider}/{model} - {total_tokens} tokens for user {user_id}")
            
            # Deduct from wallet if cost was calculated
            if estimated_cost and estimated_cost > 0:
                try:
                    from app.services.wallet_service import WalletService
                    wallet_service = WalletService()
                    from decimal import Decimal
                    
                    # Deduct cost from wallet
                    wallet_service.deduct_funds(
                        db=db,
                        user_id=user_id,
                        amount=Decimal(str(estimated_cost)),
                        description=f"LLM usage: {operation_type} ({provider}/{model}) - {total_tokens} tokens",
                        metadata={
                            "usage_metric_id": usage_metric.id,
                            "provider": provider,
                            "model": model,
                            "operation_type": operation_type,
                            "tokens": total_tokens,
                            "case_id": case_id
                        }
                    )
                    logger.debug(f"Deducted ${estimated_cost} from wallet for user {user_id}")
                except ValueError as e:
                    # Insufficient balance - log warning but don't fail the usage tracking
                    logger.warning(f"Insufficient wallet balance for user {user_id}: {e}")
                except Exception as e:
                    # Wallet deduction error - log but don't fail usage tracking
                    logger.error(f"Error deducting from wallet: {e}", exc_info=True)
            
            return usage_metric
        except Exception as e:
            logger.error(f"Error tracking usage: {e}", exc_info=True)
            db.rollback()
            raise

    def get_user_usage(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get aggregated usage statistics for a user

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            Dictionary with aggregated stats
        """
        return self.repository.get_aggregated_stats(db, user_id, start_date, end_date)

    def get_case_usage(
        self,
        db: Session,
        case_id: str
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a specific case

        Args:
            db: Database session
            case_id: Case ID

        Returns:
            Dictionary with aggregated stats for the case
        """
        metrics = self.repository.get_by_case_id(db, case_id)
        
        total_tokens = sum(m.total_tokens for m in metrics)
        prompt_tokens = sum(m.prompt_tokens for m in metrics)
        completion_tokens = sum(m.completion_tokens for m in metrics)
        total_cost = sum(float(m.estimated_cost_usd or 0) for m in metrics)
        
        return {
            "total_tokens": total_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_cost": total_cost,
            "request_count": len(metrics),
            "operations": [
                {
                    "operation_type": m.operation_type,
                    "provider": m.provider,
                    "model": m.model,
                    "tokens": m.total_tokens,
                    "cost": float(m.estimated_cost_usd or 0),
                    "timestamp": m.request_timestamp.isoformat()
                }
                for m in metrics
            ]
        }

    def get_usage_by_provider(
        self,
        db: Session,
        user_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        Get usage breakdown by provider and model

        Args:
            db: Database session
            user_id: User ID
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            List of dictionaries with provider, model, and stats
        """
        return self.repository.get_by_provider_model(db, user_id, start_date, end_date)

    def get_time_series(
        self,
        db: Session,
        user_id: str,
        start_date: datetime,
        end_date: datetime,
        group_by: str = "day"
    ) -> List[Dict[str, Any]]:
        """
        Get time-series data for usage metrics

        Args:
            db: Database session
            user_id: User ID
            start_date: Start date
            end_date: End date
            group_by: Grouping interval (day/week/month)

        Returns:
            List of dictionaries with period and aggregated stats
        """
        return self.repository.get_time_series(db, user_id, start_date, end_date, group_by)


# Singleton instance
usage_tracking_service = UsageTrackingService()

