import pytest
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from app.services.analytics_service import AnalyticsService
from app.models.case import Case, Priority
from app.models.evidence_click import EvidenceClick

class TestAnalyticsService:
    @pytest.fixture
    def db_session(self):
        return MagicMock()

    @pytest.fixture
    def service(self):
        with patch('app.services.analytics_service.EvidenceClickRepository'), \
             patch('app.services.analytics_service.CaseRepository'), \
             patch('app.services.analytics_service.CaseFileRepository'):
            return AnalyticsService()

    def test_track_evidence_click(self, service, db_session):
        """Test tracking an evidence click"""
        user_id = "user-123"
        case_id = "case-456"
        
        service.track_evidence_click(
            db=db_session,
            user_id=user_id,
            case_id=case_id,
            entity_type="diagnosis",
            entity_id="diag-789",
            source_type="file",
            file_id="file-001",
            page_number=1
        )
        
        # Verify repo create was called
        assert service.evidence_click_repo.create.called
        args, _ = service.evidence_click_repo.create.call_args
        click = args[1]
        assert isinstance(click, EvidenceClick)
        assert click.user_id == user_id
        assert click.case_id == case_id
        assert click.entity_type == "diagnosis"
        assert click.source_type == "file"

    def test_get_time_to_review_metrics_empty(self, service, db_session):
        """Test metrics calculation with no data"""
        # Mocking the query chain
        mock_query = db_session.query.return_value
        mock_query.filter.return_value = mock_query
        
        # Mocking the aggregation result
        stats_mock = MagicMock()
        stats_mock.avg_hours = None
        stats_mock.min_hours = None
        stats_mock.max_hours = None
        stats_mock.total_cases = 0
        mock_query.with_entities.return_value.first.return_value = stats_mock
        
        result = service.get_time_to_review_metrics(db_session, "user-123")
        
        assert result["average_hours"] == 0.0
        assert result["total_cases"] == 0

    @patch('app.services.analytics_service.datetime')
    def test_get_cases_per_day_range(self, mock_datetime, service, db_session):
        """Test cases per day merges uploaded and reviewed correctly"""
        user_id = "user-123"
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 1, 3)
        
        # Mock the queries
        db_session.query.return_value.filter.return_value.group_by.return_value.all.return_value = []
        
        result = service.get_cases_per_day(db_session, user_id, start_date, end_date)
        
        # Should have 3 entries (Jan 1, 2, 3)
        assert len(result) == 3
        assert result[0]["date"] == "2023-01-01"
        assert result[1]["date"] == "2023-01-02"
        assert result[2]["date"] == "2023-01-03"

    def test_get_summary_metrics(self, service, db_session):
        """Test summary metrics aggregation"""
        user_id = "user-123"
        start = datetime.utcnow() - timedelta(days=7)
        end = datetime.utcnow()
        
        with patch.object(service, 'get_time_to_review_metrics', return_value={"avg": 10}), \
             patch.object(service, 'get_cases_per_day', return_value=[]), \
             patch.object(service, 'get_evidence_click_stats', return_value={"total": 5}):
            
            result = service.get_summary_metrics(db_session, user_id, start, end)
            
            assert "time_to_review" in result
            assert "cases_per_day" in result
            assert "evidence_clicks" in result
            assert "today_cases_reviewed" in result
