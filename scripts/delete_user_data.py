"""Script to delete all data for a specific user (cases, files, S3 objects, etc.)"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.models.user import User
from app.models.case import Case
from app.models.case_file import CaseFile
from app.models.document_chunk import DocumentChunk
from app.models.extraction import ClinicalExtraction
from app.models.dashboard import DashboardSnapshot, FacetResult, SourceLink
from app.models.decision import Decision
from app.models.note import CaseNote
from app.models.usage_metrics import UsageMetrics
from app.models.user_preference import UserPreference
from app.services.s3_storage_service import s3_storage_service
from app.core.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def delete_user_data(user_identifier: str, confirm: bool = False):
    """
    Delete all data for a user including:
    - All cases and related data
    - All files from S3
    - All document chunks and vectors
    - All usage metrics
    - User preferences
    
    Args:
        user_identifier: User email or name to search for
    """
    db: Session = SessionLocal()
    
    try:
        # Find user by email or name
        user = db.query(User).filter(
            (User.email == user_identifier) | (User.name.ilike(f"%{user_identifier}%"))
        ).first()
        if not user:
            logger.error(f"User with email/name '{user_identifier}' not found")
            # Try to list all users
            try:
                all_users = db.query(User).all()
                logger.info(f"\nAvailable users:")
                for u in all_users:
                    logger.info(f"  - Email: {u.email}, Name: {u.name}")
            except Exception as e:
                logger.warning(f"Could not list users: {e}")
            return False
        
        user_id = user.id
        logger.info(f"Found user: {user.email} (ID: {user_id})")
        
        if not confirm:
            # Count what will be deleted
            case_count = db.query(Case).filter(Case.user_id == user_id).count()
            file_count = db.query(CaseFile).filter(CaseFile.user_id == user_id).count()
            chunk_count = db.query(DocumentChunk).filter(DocumentChunk.user_id == user_id).count()
            usage_count = db.query(UsageMetrics).filter(UsageMetrics.user_id == user_id).count()
            
            logger.info(f"\n⚠️  WARNING: This will delete:")
            logger.info(f"   - {case_count} cases")
            logger.info(f"   - {file_count} files")
            logger.info(f"   - {chunk_count} document chunks")
            logger.info(f"   - {usage_count} usage metrics")
            logger.info(f"   - User preferences")
            logger.info(f"\nTo confirm deletion, run with --confirm flag")
            return False
        
        # Get all cases for the user
        cases = db.query(Case).filter(Case.user_id == user_id).all()
        case_ids = [case.id for case in cases]
        
        logger.info(f"\nDeleting data for user: {user.email}")
        logger.info(f"Found {len(cases)} cases to delete")
        
        # Step 1: Delete files from S3
        logger.info("\n[1/6] Deleting files from S3...")
        deleted_files_count = 0
        for case in cases:
            case_files = db.query(CaseFile).filter(CaseFile.case_id == case.id).all()
            for case_file in case_files:
                try:
                    if settings.STORAGE_TYPE == "s3":
                        # Delete from S3
                        s3_client = s3_storage_service._get_client()
                        try:
                            s3_client.delete_object(
                                Bucket=s3_storage_service.bucket_name,
                                Key=case_file.file_path
                            )
                            deleted_files_count += 1
                            logger.info(f"  Deleted S3 file: {case_file.file_path}")
                        except Exception as e:
                            logger.warning(f"  Failed to delete S3 file {case_file.file_path}: {e}")
                    else:
                        # Local storage - delete file
                        import os
                        if os.path.exists(case_file.file_path):
                            os.remove(case_file.file_path)
                            deleted_files_count += 1
                            logger.info(f"  Deleted local file: {case_file.file_path}")
                except Exception as e:
                    logger.warning(f"  Error deleting file {case_file.file_name}: {e}")
        
        logger.info(f"  Deleted {deleted_files_count} files from storage")
        
        # Step 2: Delete document chunks (vectors are stored within the chunks in pgvector)
        logger.info("\n[2/6] Deleting document chunks...")
        
        # Delete chunks from database
        chunk_count = db.query(DocumentChunk).filter(DocumentChunk.user_id == user_id).delete()
        logger.info(f"  Deleted {chunk_count} document chunks from database")
        db.commit()
        
        # Step 3: Delete dashboard-related data
        logger.info("\n[3/6] Deleting dashboard snapshots and facets...")
        for case_id in case_ids:
            # Get all snapshots for this case
            snapshots = db.query(DashboardSnapshot).filter(DashboardSnapshot.case_id == case_id).all()
            for snapshot in snapshots:
                # Delete source links
                db.query(SourceLink).filter(SourceLink.facet_id.in_(
                    db.query(FacetResult.id).filter(FacetResult.snapshot_id == snapshot.id)
                )).delete()
                # Delete facet results
                db.query(FacetResult).filter(FacetResult.snapshot_id == snapshot.id).delete()
            # Delete snapshots
            db.query(DashboardSnapshot).filter(DashboardSnapshot.case_id == case_id).delete()
        db.commit()
        logger.info("  Deleted dashboard data")
        
        # Step 4: Delete case-related data (extractions, decisions, notes)
        logger.info("\n[4/6] Deleting case-related data...")
        extraction_count = db.query(ClinicalExtraction).filter(ClinicalExtraction.user_id == user_id).delete()
        decision_count = db.query(Decision).filter(Decision.case_id.in_(case_ids)).delete()
        note_count = db.query(CaseNote).filter(CaseNote.case_id.in_(case_ids)).delete()
        db.commit()
        logger.info(f"  Deleted {extraction_count} extractions, {decision_count} decisions, {note_count} notes")
        
        # Step 5: Delete case files and cases
        logger.info("\n[5/6] Deleting case files and cases...")
        file_count = db.query(CaseFile).filter(CaseFile.user_id == user_id).delete()
        case_count = db.query(Case).filter(Case.user_id == user_id).delete()
        db.commit()
        logger.info(f"  Deleted {file_count} case files and {case_count} cases")
        
        # Step 6: Delete usage metrics and preferences
        logger.info("\n[6/6] Deleting usage metrics and preferences...")
        usage_count = db.query(UsageMetrics).filter(UsageMetrics.user_id == user_id).delete()
        preference = db.query(UserPreference).filter(UserPreference.user_id == user_id).first()
        if preference:
            db.delete(preference)
            logger.info("  Deleted user preferences")
        db.commit()
        logger.info(f"  Deleted {usage_count} usage metrics")
        
        logger.info(f"\n✅ Successfully deleted all data for user: {user.email}")
        return True
        
    except Exception as e:
        logger.error(f"Error deleting user data: {e}", exc_info=True)
        db.rollback()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Delete all data for a user")
    parser.add_argument("identifier", help="User email or name")
    parser.add_argument("--confirm", action="store_true", help="Confirm deletion (required to actually delete)")
    
    args = parser.parse_args()
    
    success = delete_user_data(args.identifier, confirm=args.confirm)
    sys.exit(0 if success else 1)

