"""Database index definitions for performance optimization

This module defines recommended indexes for frequently queried fields.
These should be added via Alembic migrations.
"""

# Recommended indexes by model:

"""
Case Model Indexes:
- idx_case_user_id_status: (user_id, status) - Composite index for user case queries
- idx_case_status_created: (status, created_at) - For filtering and sorting
- idx_case_case_number_user: (case_number, user_id) - For case number lookups
- idx_case_created_at: (created_at) - For date-based sorting

CaseFile Model Indexes:
- idx_case_file_case_id: (case_id) - For loading case files (already exists if FK)
- idx_case_file_case_id_order: (case_id, file_order) - For ordered file loading

ClinicalExtraction Model Indexes:
- idx_extraction_case_id: (case_id) - For case extraction lookups
- idx_extraction_case_user: (case_id, user_id) - Composite for user-scoped queries

DocumentChunk Model Indexes:
- idx_chunk_case_id: (case_id) - For case chunk queries
- idx_chunk_case_section: (case_id, section_type) - For section-filtered queries
- idx_chunk_vector_id: (vector_id) - For vector lookups (if using vector search)

User Model Indexes:
- idx_user_email: (email) - For email-based lookups (should be unique)

DashboardSnapshot Model Indexes:
- idx_snapshot_case_user: (case_id, user_id) - For user dashboard queries
- idx_snapshot_case_created: (case_id, created_at) - For latest snapshot queries

FacetResult Model Indexes:
- idx_facet_snapshot_type: (snapshot_id, facet_type) - For facet lookups

Transaction Model Indexes:
- idx_transaction_user_created: (user_id, created_at) - For user transaction history

EvidenceClick Model Indexes:
- idx_click_user_created: (user_id, created_at) - For user analytics
- idx_click_case_user: (case_id, user_id) - For case-specific analytics

ConversationMessage Model Indexes:
- idx_conversation_case_user: (case_id, user_id) - Already exists in model
- idx_conversation_case_created: (case_id, created_at) - Already exists in model
"""


