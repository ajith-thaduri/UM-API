"""Add wallet and transaction tables for user balance management

Revision ID: 20251223_1504
Revises: 20251223_1216
Create Date: 2025-12-23 15:04:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '20251223_1504'
down_revision: Union[str, None] = '20251223_1216'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create wallets table
    op.create_table(
        'wallets',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('balance', sa.Numeric(precision=10, scale=2), nullable=False, server_default='50.00'),
        sa.Column('currency', sa.String(), nullable=False, server_default='USD'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id')
    )
    
    # Create indexes for wallets
    op.create_index(op.f('ix_wallets_id'), 'wallets', ['id'], unique=False)
    op.create_index(op.f('ix_wallets_user_id'), 'wallets', ['user_id'], unique=True)
    op.create_index('idx_wallet_user', 'wallets', ['user_id'], unique=False)
    
    # Create transactions table
    op.create_table(
        'transactions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('wallet_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('type', sa.String(), nullable=False),  # 'credit' or 'debit'
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pending'),  # 'pending', 'completed', 'failed'
        sa.Column('payment_method', sa.String(), nullable=True),  # 'stripe', 'trial', 'refund', 'usage'
        sa.Column('stripe_payment_intent_id', sa.String(), nullable=True),
        sa.Column('extra_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['wallet_id'], ['wallets.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for transactions
    op.create_index(op.f('ix_transactions_id'), 'transactions', ['id'], unique=False)
    op.create_index(op.f('ix_transactions_wallet_id'), 'transactions', ['wallet_id'], unique=False)
    op.create_index(op.f('ix_transactions_user_id'), 'transactions', ['user_id'], unique=False)
    op.create_index(op.f('ix_transactions_type'), 'transactions', ['type'], unique=False)
    op.create_index(op.f('ix_transactions_status'), 'transactions', ['status'], unique=False)
    op.create_index(op.f('ix_transactions_stripe_payment_intent_id'), 'transactions', ['stripe_payment_intent_id'], unique=False)
    op.create_index(op.f('ix_transactions_created_at'), 'transactions', ['created_at'], unique=False)
    
    # Create composite indexes for common queries
    op.create_index('idx_transaction_user', 'transactions', ['user_id'], unique=False)
    op.create_index('idx_transaction_wallet', 'transactions', ['wallet_id'], unique=False)
    op.create_index('idx_transaction_created', 'transactions', ['created_at'], unique=False)
    op.create_index('idx_transaction_type_status', 'transactions', ['type', 'status'], unique=False)
    
    # Seed existing users with $50 trial balance
    # This will create wallets for all existing users
    connection = op.get_bind()
    connection.execute(sa.text("""
        INSERT INTO wallets (id, user_id, balance, currency, created_at, updated_at)
        SELECT 
            gen_random_uuid()::text,
            id,
            50.00,
            'USD',
            NOW(),
            NOW()
        FROM users
        WHERE id NOT IN (SELECT user_id FROM wallets)
    """))


def downgrade() -> None:
    # Drop composite indexes
    op.drop_index('idx_transaction_type_status', table_name='transactions')
    op.drop_index('idx_transaction_created', table_name='transactions')
    op.drop_index('idx_transaction_wallet', table_name='transactions')
    op.drop_index('idx_transaction_user', table_name='transactions')
    
    # Drop single column indexes for transactions
    op.drop_index(op.f('ix_transactions_created_at'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_stripe_payment_intent_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_status'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_type'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_user_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_wallet_id'), table_name='transactions')
    op.drop_index(op.f('ix_transactions_id'), table_name='transactions')
    
    # Drop transactions table
    op.drop_table('transactions')
    
    # Drop indexes for wallets
    op.drop_index('idx_wallet_user', table_name='wallets')
    op.drop_index(op.f('ix_wallets_user_id'), table_name='wallets')
    op.drop_index(op.f('ix_wallets_id'), table_name='wallets')
    
    # Drop wallets table
    op.drop_table('wallets')

