"""Unit tests for merged clinical state (Phase 2) — no DB."""

from app.services.version_merge_service import compute_merged_clinical_state


def test_compute_merged_clinical_state_empty_prior():
    current = {
        "diagnoses": [{"name": "Hypertension", "source_file_id": "f1"}],
        "medications": [],
    }
    out = compute_merged_clinical_state(None, current, ["f1"])
    assert out["domain_stats"]["diagnoses"]["current_count"] == 1
    assert "DIAGNOSES" in out["section_change_hints"]
    assert out["delta_by_domain"]["diagnoses"]


def test_compute_merged_clinical_state_no_change_when_identical():
    ed = {"diagnoses": [{"name": "DM2"}], "medications": []}
    out = compute_merged_clinical_state(ed, ed, [])
    assert out["section_change_hints"].get("DIAGNOSES") == "unchanged"


def test_compute_merged_attribution_to_new_docs_only():
    prior = {"diagnoses": [{"name": "Old", "source_file_id": "base"}]}
    current = {
        "diagnoses": [
            {"name": "Old", "source_file_id": "base"},
            {"name": "New finding", "source_file_id": "new1"},
        ]
    }
    out = compute_merged_clinical_state(prior, current, ["new1"])
    assert "New finding" in (out["delta_by_domain"].get("diagnoses") or [])
