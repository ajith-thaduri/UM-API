"""Wallet schemas for API requests and responses"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from decimal import Decimal


class WalletBalanceResponse(BaseModel):
    """Wallet balance response"""
    balance: float
    currency: str
    is_low_balance: bool
    threshold: float
    remaining: float

    class Config:
        from_attributes = True


class WalletSummaryResponse(BaseModel):
    """Comprehensive wallet summary response"""
    balance: float
    currency: str
    is_low_balance: bool
    threshold: float
    total_transactions: int
    recent_transaction_count: int
    created_at: Optional[str]
    updated_at: Optional[str]

    class Config:
        from_attributes = True


class TransactionResponse(BaseModel):
    """Transaction response"""
    id: str
    wallet_id: str
    user_id: str
    type: str  # "credit" or "debit"
    amount: float
    description: Optional[str]
    status: str  # "pending", "completed", "failed"
    payment_method: Optional[str]
    stripe_payment_intent_id: Optional[str]
    extra_metadata: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionListResponse(BaseModel):
    """List of transactions response"""
    transactions: List[TransactionResponse]
    total: int
    limit: int
    offset: int


class AddFundsRequest(BaseModel):
    """Request to add funds to wallet"""
    amount: float = Field(..., gt=0, description="Amount to add (must be > 0)")
    payment_method: str = Field(default="stripe", description="Payment method")


class CreatePaymentIntentRequest(BaseModel):
    """Request to create a payment intent"""
    amount: float = Field(..., gt=0, description="Payment amount (must be > 0)")
    currency: str = Field(default="usd", description="Currency code")
    metadata: Optional[Dict[str, Any]] = None


class PaymentIntentResponse(BaseModel):
    """Payment intent response"""
    id: str
    amount: int  # Amount in cents
    currency: str
    status: str
    client_secret: str
    metadata: Optional[Dict[str, Any]]


class ConfirmPaymentRequest(BaseModel):
    """Request to confirm a payment"""
    payment_intent_id: str
    payment_method: Optional[Dict[str, Any]] = None


class ConfirmPaymentResponse(BaseModel):
    """Payment confirmation response"""
    payment_intent_id: str
    status: str
    amount: float
    transaction_id: Optional[str] = None
    error: Optional[str] = None


class LowBalanceCheckResponse(BaseModel):
    """Low balance check response"""
    is_low: bool
    balance: float
    threshold: float
    remaining: float

