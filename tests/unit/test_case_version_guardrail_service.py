"""Unit tests for branch upload guardrail helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import case_version_guardrail_service as cvg


def test_best_text_duplicate_none_for_short_text():
    assert cvg._best_text_duplicate("short", [("1", "a.pdf", "x" * 200)]) is None


def test_best_text_duplicate_finds_high_match():
    long_a = ("patient john doe admitted for observation " * 25).lower()
    long_b = long_a
    best = cvg._best_text_duplicate(long_b, [("fid", "old.pdf", long_a)])
    assert best is not None
    assert best["file_id"] == "fid"
    assert best["similarity"] >= 0.85


def test_name_similarity_empty_extracted():
    assert cvg._name_similarity("Jane Doe", None) == 1.0


def test_name_similarity_mismatch():
    r = cvg._name_similarity("Jane Marie Doe", "Robert Smith")
    assert r < cvg.PATIENT_NAME_RATIO_MIN


@pytest.mark.asyncio
async def test_evaluate_branch_empty_uploads():
    db = MagicMock()
    case = MagicMock()
    case.id = "case-1"
    case.patient_name = "Test Patient"
    out = await cvg.evaluate_branch_new_uploads(
        db,
        case=case,
        base_version_id="bv-1",
        user_id="u1",
        uploads=[],
        exclude_existing_file_ids=None,
    )
    assert out["has_warnings"] is False
    assert out["files"] == []


@pytest.mark.asyncio
@patch.object(cvg, "_llm_patient_alignment", new_callable=AsyncMock, return_value=(None, ""))
@patch.object(cvg.extraction_repository, "get_by_case_id_and_version", return_value=None)
@patch.object(cvg, "pdf_analyzer_service")
@patch.object(cvg, "_collect_existing_leading_texts", return_value=[])
@patch.object(cvg, "leading_pdf_text", return_value="x" * 120)
async def test_evaluate_flags_non_medical(
    _mock_llm, _mock_ext, mock_pdf_analyzer, mock_collect, mock_lead
):
    db = MagicMock()
    case = MagicMock()
    case.id = "case-1"
    case.patient_name = "Test Patient"

    fa = MagicMock()
    fa.detected_type = "non_medical_resume"
    fa.file_name = "cv.pdf"
    analysis = MagicMock()
    analysis.files = [fa]
    analysis.patient_info = MagicMock()
    analysis.patient_info.name = None
    mock_pdf_analyzer.analyze_for_upload = AsyncMock(return_value=analysis)

    out = await cvg.evaluate_branch_new_uploads(
        db,
        case=case,
        base_version_id="bv-1",
        user_id="u1",
        uploads=[("/tmp/x.pdf", "cv.pdf")],
        exclude_existing_file_ids=set(),
    )
    assert out["has_warnings"] is True
    assert out["files"][0]["issues"]
    assert any(i["code"] == "non_medical" for i in out["files"][0]["issues"])
