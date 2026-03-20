"""Wallet API endpoints"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from decimal import Decimal

from app.db.session import get_db
from app.api.endpoints.auth import get_current_user
from app.models.user import User
from app.models.transaction import TransactionType
from app.services.wallet_service import WalletService
from app.services.mock_stripe_service import mock_stripe_service
from app.schemas.wallet import (
    WalletBalanceResponse,
    WalletSummaryResponse,
    TransactionResponse,
    TransactionListResponse,
    AddFundsRequest,
    CreatePaymentIntentRequest,
    PaymentIntentResponse,
    ConfirmPaymentRequest,
    ConfirmPaymentResponse,
    LowBalanceCheckResponse
)

router = APIRouter()
wallet_service = WalletService()


@router.get("/wallet/balance", response_model=WalletBalanceResponse)
async def get_wallet_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current wallet balance"""
    try:
        balance = wallet_service.get_balance(db, current_user.id)
        low_balance_check = wallet_service.check_low_balance(db, current_user.id)
        
        return WalletBalanceResponse(
            balance=float(balance),
            currency="USD",
            is_low_balance=low_balance_check["is_low"],
            threshold=low_balance_check["threshold"],
            remaining=low_balance_check["remaining"]
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving wallet balance: {str(e)}"
        )


@router.get("/wallet/summary", response_model=WalletSummaryResponse)
async def get_wallet_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive wallet summary"""
    try:
        summary = wallet_service.get_wallet_summary(db, current_user.id)
        return WalletSummaryResponse(**summary)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving wallet summary: {str(e)}"
        )


@router.get("/wallet/transactions", response_model=TransactionListResponse)
async def get_transactions(
    limit: int = 50,
    offset: int = 0,
    transaction_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get transaction history"""
    try:
        # Validate transaction type
        tx_type = None
        if transaction_type:
            try:
                tx_type = TransactionType(transaction_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid transaction type: {transaction_type}. Must be 'credit' or 'debit'"
                )

        transactions = wallet_service.get_transaction_history(
            db, current_user.id, limit=limit, offset=offset, transaction_type=tx_type
        )
        
        # Count total transactions
        from app.repositories.transaction_repository import TransactionRepository
        transaction_repo = TransactionRepository()
        total = transaction_repo.count_by_user(db, current_user.id, transaction_type=tx_type)

        return TransactionListResponse(
            transactions=[TransactionResponse.model_validate(tx) for tx in transactions],
            total=total,
            limit=limit,
            offset=offset
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving transactions: {str(e)}"
        )


@router.get("/wallet/low-balance-check", response_model=LowBalanceCheckResponse)
async def check_low_balance(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if wallet balance is low"""
    try:
        result = wallet_service.check_low_balance(db, current_user.id)
        return LowBalanceCheckResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error checking balance: {str(e)}"
        )


@router.post("/wallet/mock-stripe/create-intent", response_model=PaymentIntentResponse)
async def create_payment_intent(
    request: CreatePaymentIntentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a mock Stripe payment intent"""
    try:
        amount = Decimal(str(request.amount))
        payment_intent = await mock_stripe_service.create_payment_intent(
            amount=amount,
            currency=request.currency,
            metadata={"user_id": current_user.id, **request.metadata} if request.metadata else {"user_id": current_user.id}
        )
        
        return PaymentIntentResponse(
            id=payment_intent["id"],
            amount=payment_intent["amount"],
            currency=payment_intent["currency"],
            status=payment_intent["status"],
            client_secret=payment_intent["client_secret"],
            metadata=payment_intent.get("metadata")
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating payment intent: {str(e)}"
        )


@router.post("/wallet/mock-stripe/confirm", response_model=ConfirmPaymentResponse)
async def confirm_payment(
    request: ConfirmPaymentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Confirm a mock Stripe payment"""
    try:
        # Get payment intent status
        payment_intent = await mock_stripe_service.get_payment_status(request.payment_intent_id)
        
        # Confirm payment (simulates processing)
        confirmed_intent = await mock_stripe_service.confirm_payment(
            request.payment_intent_id,
            payment_method=request.payment_method
        )

        if confirmed_intent["status"] == "succeeded":
            # Add funds to wallet
            amount = Decimal(str(confirmed_intent["amount"] / 100))  # Convert from cents
            transaction = wallet_service.add_funds(
                db=db,
                user_id=current_user.id,
                amount=amount,
                payment_method="stripe",
                description=f"Payment via Stripe (mock)",
                stripe_payment_intent_id=request.payment_intent_id,
                metadata={"payment_intent": confirmed_intent}
            )

            return ConfirmPaymentResponse(
                payment_intent_id=request.payment_intent_id,
                status="succeeded",
                amount=float(amount),
                transaction_id=transaction.id
            )
        else:
            # Payment failed
            error_message = confirmed_intent.get("last_payment_error", {}).get("message", "Payment failed")
            return ConfirmPaymentResponse(
                payment_intent_id=request.payment_intent_id,
                status="failed",
                amount=float(confirmed_intent["amount"] / 100),
                error=error_message
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error confirming payment: {str(e)}"
        )


@router.post("/wallet/add-funds")
async def add_funds(
    request: AddFundsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add funds to wallet (direct method, bypasses Stripe)"""
    try:
        amount = Decimal(str(request.amount))
        transaction = wallet_service.add_funds(
            db=db,
            user_id=current_user.id,
            amount=amount,
            payment_method=request.payment_method,
            description=f"Funds added via {request.payment_method}"
        )

        return TransactionResponse.model_validate(transaction)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error adding funds: {str(e)}"
        )


@router.get("/wallet/transactions/grouped", response_model=List[Dict[str, Any]])
async def get_grouped_transactions(
    limit: int = 50,
    offset: int = 0,
    transaction_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get transactions grouped by case"""
    try:
        tx_type = None
        if transaction_type:
            try:
                tx_type = TransactionType(transaction_type.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid transaction type: {transaction_type}"
                )
        
        grouped = wallet_service.get_transactions_grouped_by_case(
            db, current_user.id, limit=limit, offset=offset, transaction_type=tx_type
        )
        return grouped
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving grouped transactions: {str(e)}"
        )


@router.get("/wallet/transactions/case/{case_id}", response_model=Dict[str, Any])
async def get_case_transaction_details(
    case_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed breakdown of transactions for a specific case"""
    try:
        details = wallet_service.get_case_transaction_details(
            db, current_user.id, case_id
        )
        return details
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving case details: {str(e)}"
        )

