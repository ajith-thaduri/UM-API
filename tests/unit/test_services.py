import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from app.services.wallet_service import WalletService
from app.services.llm_service import LLMService
from app.models.wallet import Wallet
from app.models.transaction import Transaction

def test_wallet_service_add_funds_logic():
    """Test that add_funds correctly calculates the new balance."""
    # Mock dependencies
    mock_db = MagicMock()
    mock_wallet_repo = MagicMock()
    
    # Setup service
    service = WalletService()
    service.wallet_repo = mock_wallet_repo
    
    # Setup mock data
    user_id = "test-user-123"
    initial_balance = Decimal("50.00")
    amount_to_add = Decimal("25.50")
    
    mock_wallet = Wallet(id="wallet-1", user_id=user_id, balance=initial_balance)
    mock_wallet_repo.get_by_user_id.return_value = mock_wallet
    
    # Execute
    transaction = service.add_funds(mock_db, user_id, amount_to_add)
    
    # Assert
    assert mock_wallet.balance == Decimal("75.50")
    assert mock_db.add.called
    assert mock_db.commit.called

@pytest.mark.asyncio
async def test_llm_service_extraction_mocked():
    """Test that LLMService structure is correct and can be instantiated."""
    # Mock the LLM factory to return a mock service
    with patch("app.services.llm_service.get_llm_service_instance") as mock_factory:
        mock_llm_instance = MagicMock()
        mock_llm_instance.is_available.return_value = False  # Force mock extraction
        mock_factory.return_value = mock_llm_instance
        
        service = LLMService()
        
        # Execute - should return mock extraction since LLM is not available
        result = await service.extract_clinical_information("Sample medical text")
        
        # Assert - should return mock data structure
        assert isinstance(result, dict)
        assert "diagnoses" in result or "medications" in result  # Mock extraction has these keys
