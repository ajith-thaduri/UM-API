"""Mock Stripe service for simulating payment processing"""

import uuid
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class MockStripeService:
    """Mock Stripe service that simulates payment processing"""

    def __init__(self):
        # Store payment intents in memory (in production, this would be in a database)
        self._payment_intents: Dict[str, Dict[str, Any]] = {}
        # Simulate payment failure rate (10% for testing)
        self._failure_rate = 0.1

    async def create_payment_intent(
        self,
        amount: Decimal,
        currency: str = "usd",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a mock payment intent

        Args:
            amount: Payment amount
            currency: Currency code (default: usd)
            metadata: Optional metadata

        Returns:
            Dictionary with payment intent details
        """
        payment_intent_id = f"pi_mock_{uuid.uuid4().hex[:24]}"
        
        payment_intent = {
            "id": payment_intent_id,
            "object": "payment_intent",
            "amount": int(amount * 100),  # Convert to cents
            "currency": currency.lower(),
            "status": "requires_payment_method",
            "client_secret": f"{payment_intent_id}_secret_mock",
            "metadata": metadata or {},
            "created": int(datetime.utcnow().timestamp()),
            "confirmation_method": "manual"
        }

        self._payment_intents[payment_intent_id] = payment_intent
        logger.info(f"Created mock payment intent {payment_intent_id} for ${amount}")

        return payment_intent

    async def confirm_payment(
        self,
        payment_intent_id: str,
        payment_method: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Confirm a mock payment (simulates processing delay)

        Args:
            payment_intent_id: Payment intent ID
            payment_method: Optional payment method details (card info, etc.)

        Returns:
            Dictionary with confirmed payment intent details

        Raises:
            ValueError: If payment intent not found
        """
        if payment_intent_id not in self._payment_intents:
            raise ValueError(f"Payment intent {payment_intent_id} not found")

        payment_intent = self._payment_intents[payment_intent_id]

        # Simulate processing delay (2-3 seconds)
        await asyncio.sleep(2.5)

        # Simulate payment failure (10% chance)
        import random
        if random.random() < self._failure_rate:
            payment_intent["status"] = "payment_failed"
            payment_intent["last_payment_error"] = {
                "type": "card_error",
                "code": "card_declined",
                "message": "Your card was declined (mock simulation)"
            }
            logger.warning(f"Mock payment {payment_intent_id} failed (simulated)")
        else:
            payment_intent["status"] = "succeeded"
            payment_intent["charges"] = {
                "data": [{
                    "id": f"ch_mock_{uuid.uuid4().hex[:24]}",
                    "amount": payment_intent["amount"],
                    "currency": payment_intent["currency"],
                    "status": "succeeded",
                    "paid": True
                }]
            }
            logger.info(f"Mock payment {payment_intent_id} succeeded")

        payment_intent["updated"] = int(datetime.utcnow().timestamp())
        return payment_intent

    async def get_payment_status(self, payment_intent_id: str) -> Dict[str, Any]:
        """
        Get payment intent status

        Args:
            payment_intent_id: Payment intent ID

        Returns:
            Dictionary with payment intent details

        Raises:
            ValueError: If payment intent not found
        """
        if payment_intent_id not in self._payment_intents:
            raise ValueError(f"Payment intent {payment_intent_id} not found")

        return self._payment_intents[payment_intent_id]

    def set_failure_rate(self, rate: float):
        """
        Set the payment failure rate for testing

        Args:
            rate: Failure rate between 0.0 and 1.0
        """
        self._failure_rate = max(0.0, min(1.0, rate))
        logger.info(f"Mock Stripe failure rate set to {self._failure_rate * 100}%")

    def clear_payment_intents(self):
        """Clear all stored payment intents (for testing)"""
        self._payment_intents.clear()
        logger.info("Cleared all mock payment intents")


# Singleton instance
mock_stripe_service = MockStripeService()

