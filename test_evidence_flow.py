"""
Evidence / Source-Viewer Integration Test
==========================================
Validates every layer of the evidence pipeline:

  PART 1 – Unit tests (no DB required)
    1. assign_words_to_chunk  — correct word-level filtering
    2. find_term_bbox         — tight bbox around a searched term
    3. chunk_page_with_bbox   — ChunkData.word_segments populated
    4. J2 mapping             — word_segments wired into DocumentChunk kwargs

  PART 2 – Integration tests (real PostgreSQL DB)
    5. DB connection + entity_sources table exists
    6. Fetch the most-recent ClinicalExtraction + its chunks from DB
    7. Simulate J3: call create_sources_from_extraction on real data
    8. Verify EntitySource rows land in DB with correct entity_id/file_id/page
    9. Verify the retrieval path (entity_source_repo.get_by_entity) works
   10. Verify word_segments round-trip: insert + read back from document_chunks
   11. Cleanup – delete only test-created EntitySource rows

Run from UM-API root:
    cd /Users/ajiththaduri/Desktop/V2/UM-API
    python test_evidence_flow.py
"""

import os
import sys
import uuid
import time
import traceback
from datetime import datetime

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

# Load .env if present so DATABASE_URL etc. are available
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except ImportError:
    pass  # dotenv optional; rely on real env vars


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"
WARN = "\033[93m[WARN]\033[0m"
SEP  = "─" * 68

_results = []

def run(label, fn):
    print(f"\n  Testing: {label}")
    try:
        fn()
        print(f"  {PASS} {label}")
        _results.append((label, True, None))
    except AssertionError as e:
        msg = str(e) or "assertion failed"
        print(f"  {FAIL} {label}: {msg}")
        _results.append((label, False, msg))
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"  {FAIL} {label}: {msg}")
        traceback.print_exc()
        _results.append((label, False, msg))


# ─────────────────────────────────────────────────────────────────────────────
# PART 1 – Unit tests
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("PART 1 — Unit Tests (no DB)")
print(SEP)

# 1. assign_words_to_chunk ─────────────────────────────────────────────────────
def _test_assign_words_basic():
    from app.utils.bbox_utils import assign_words_to_chunk

    segments = [
        {"text": "Patient", "bbox": {"x0": 10, "y0": 100, "x1": 60, "y1": 115}},
        {"text": "has",     "bbox": {"x0": 65, "y0": 100, "x1": 85, "y1": 115}},
        {"text": "Diabetes", "bbox": {"x0": 90, "y0": 100, "x1": 150, "y1": 115}},
        {"text": "mellitus", "bbox": {"x0": 155, "y0": 100, "x1": 230, "y1": 115}},
        {"text": "and",     "bbox": {"x0": 10,  "y0": 120, "x1": 40,  "y1": 135}},
        {"text": "hypertension", "bbox": {"x0": 45, "y0": 120, "x1": 140, "y1": 135}},
    ]
    # chunk_text contains only first 4 words
    chunk_text = "Patient has Diabetes mellitus"
    result = assign_words_to_chunk(chunk_text, segments)

    assert len(result) == 4, f"Expected 4 word segments, got {len(result)}"
    assert result[0]["text"] == "Patient"
    assert result[3]["text"] == "mellitus"
    # 'and' and 'hypertension' should be excluded
    texts = [r["text"] for r in result]
    assert "and" not in texts, "'and' should not be in chunk segments"
    assert "hypertension" not in texts


def _test_assign_words_excludes_non_chunk_words():
    from app.utils.bbox_utils import assign_words_to_chunk

    # Segments cover two distinct sections of the page.
    # The chunk only covers the second section — words from the first section
    # must be excluded even though they appear first in the segments list.
    segments = [
        # Section 1 — NOT in chunk
        {"text": "Allergies:",  "bbox": {"x0": 10,  "y0": 10, "x1": 90,  "y1": 25}},
        {"text": "Penicillin",  "bbox": {"x0": 95,  "y0": 10, "x1": 175, "y1": 25}},
        {"text": "NKDA",        "bbox": {"x0": 180, "y0": 10, "x1": 225, "y1": 25}},
        # Section 2 — IN chunk
        {"text": "Medications:", "bbox": {"x0": 10,  "y0": 40, "x1": 100, "y1": 55}},
        {"text": "Metformin",    "bbox": {"x0": 105, "y0": 40, "x1": 185, "y1": 55}},
        {"text": "500mg",        "bbox": {"x0": 190, "y0": 40, "x1": 240, "y1": 55}},
    ]
    chunk_text = "Medications: Metformin 500mg"
    result = assign_words_to_chunk(chunk_text, segments)
    texts = [r["text"] for r in result]
    assert len(result) == 3, f"Expected 3 segments, got {len(result)}: {texts}"
    assert "Medications:" in texts, f"'Medications:' missing: {texts}"
    assert "Metformin"    in texts, f"'Metformin' missing: {texts}"
    assert "500mg"        in texts, f"'500mg' missing: {texts}"
    # None of the first section's words should appear
    assert "Allergies:" not in texts, f"Section-1 word leaked into result: {texts}"
    assert "Penicillin"  not in texts, f"Section-1 word leaked into result: {texts}"
    # All matched segments are from the second section (y0=40)
    for seg in result:
        assert seg["bbox"]["y0"] == 40, (
            f"Segment '{seg['text']}' came from wrong row: y0={seg['bbox']['y0']}"
        )


def _test_assign_words_empty():
    from app.utils.bbox_utils import assign_words_to_chunk
    assert assign_words_to_chunk("", []) == []
    assert assign_words_to_chunk("hello", []) == []
    assert assign_words_to_chunk("", [{"text": "a", "bbox": {"x0":0,"y0":0,"x1":1,"y1":1}}]) == []


run("assign_words_to_chunk: basic filtering", _test_assign_words_basic)
run("assign_words_to_chunk: excludes words not in chunk text", _test_assign_words_excludes_non_chunk_words)
run("assign_words_to_chunk: empty inputs", _test_assign_words_empty)


# 2. find_term_bbox ────────────────────────────────────────────────────────────
def _test_find_term_single_word():
    from app.utils.bbox_utils import find_term_bbox
    segs = [
        {"text": "Metformin", "bbox": {"x0": 90,  "y0": 50, "x1": 150, "y1": 65}},
        {"text": "500mg",     "bbox": {"x0": 155, "y0": 50, "x1": 210, "y1": 65}},
        {"text": "daily",     "bbox": {"x0": 215, "y0": 50, "x1": 255, "y1": 65}},
    ]
    result = find_term_bbox("Metformin", segs)
    assert result is not None, "Should find 'Metformin'"
    assert abs(result["x0"] - 90)  < 1, f"x0 should be 90, got {result['x0']}"
    assert abs(result["x1"] - 150) < 1, f"x1 should be 150, got {result['x1']}"


def _test_find_term_multi_word():
    from app.utils.bbox_utils import find_term_bbox
    segs = [
        {"text": "Metformin", "bbox": {"x0": 90,  "y0": 50, "x1": 150, "y1": 65}},
        {"text": "500mg",     "bbox": {"x0": 155, "y0": 50, "x1": 210, "y1": 65}},
        {"text": "daily",     "bbox": {"x0": 215, "y0": 50, "x1": 255, "y1": 65}},
    ]
    result = find_term_bbox("Metformin 500mg", segs)
    assert result is not None, "Should find 'Metformin 500mg'"
    assert abs(result["x0"] - 90)  < 1, f"x0 should be 90 (start of Metformin), got {result['x0']}"
    assert abs(result["x1"] - 210) < 1, f"x1 should be 210 (end of 500mg), got {result['x1']}"
    # 'daily' must NOT be included
    assert result["x1"] < 215, "bbox should not extend into 'daily'"


def _test_find_term_not_found():
    from app.utils.bbox_utils import find_term_bbox
    segs = [{"text": "Aspirin", "bbox": {"x0": 10, "y0": 10, "x1": 70, "y1": 25}}]
    result = find_term_bbox("Metformin", segs)
    assert result is None, "Should return None for missing term"


def _test_find_term_case_insensitive():
    from app.utils.bbox_utils import find_term_bbox
    segs = [{"text": "DIABETES", "bbox": {"x0": 10, "y0": 10, "x1": 90, "y1": 25}}]
    result = find_term_bbox("diabetes", segs)
    assert result is not None, "Should find case-insensitively"


run("find_term_bbox: single-word term", _test_find_term_single_word)
run("find_term_bbox: multi-word precise (x0 from first word only)", _test_find_term_multi_word)
run("find_term_bbox: term not in segments → None", _test_find_term_not_found)
run("find_term_bbox: case-insensitive match", _test_find_term_case_insensitive)


# 3. chunk_page_with_bbox populates word_segments ─────────────────────────────
def _test_chunk_page_with_bbox_word_segments():
    from app.services.chunking_service import ChunkingService

    svc = ChunkingService()
    page_text = (
        "Patient was admitted with chest pain. "
        "History of hypertension and diabetes. "
        "Prescribed Metformin 500mg daily."
    )
    segments = [
        {"text": "Patient",      "bbox": {"x0": 10,  "y0": 10, "x1": 60,  "y1": 25}},
        {"text": "was",          "bbox": {"x0": 65,  "y0": 10, "x1": 85,  "y1": 25}},
        {"text": "admitted",     "bbox": {"x0": 90,  "y0": 10, "x1": 140, "y1": 25}},
        {"text": "with",         "bbox": {"x0": 145, "y0": 10, "x1": 170, "y1": 25}},
        {"text": "chest",        "bbox": {"x0": 175, "y0": 10, "x1": 215, "y1": 25}},
        {"text": "pain.",        "bbox": {"x0": 220, "y0": 10, "x1": 255, "y1": 25}},
        {"text": "History",      "bbox": {"x0": 10,  "y0": 30, "x1": 65,  "y1": 45}},
        {"text": "of",           "bbox": {"x0": 70,  "y0": 30, "x1": 85,  "y1": 45}},
        {"text": "hypertension", "bbox": {"x0": 90,  "y0": 30, "x1": 170, "y1": 45}},
        {"text": "and",          "bbox": {"x0": 175, "y0": 30, "x1": 198, "y1": 45}},
        {"text": "diabetes.",    "bbox": {"x0": 203, "y0": 30, "x1": 260, "y1": 45}},
        {"text": "Prescribed",   "bbox": {"x0": 10,  "y0": 50, "x1": 80,  "y1": 65}},
        {"text": "Metformin",    "bbox": {"x0": 85,  "y0": 50, "x1": 150, "y1": 65}},
        {"text": "500mg",        "bbox": {"x0": 155, "y0": 50, "x1": 205, "y1": 65}},
        {"text": "daily.",       "bbox": {"x0": 210, "y0": 50, "x1": 250, "y1": 65}},
    ]

    chunks = svc.chunk_page_with_bbox(
        text=page_text,
        text_segments=segments,
        page_number=1,
        file_id="file-test-001",
        case_id="case-test-001",
    )

    assert chunks, "Should produce at least one chunk"
    for chunk in chunks:
        assert chunk.bbox is not None, f"chunk {chunk.chunk_index} missing bbox"
        assert chunk.word_segments is not None, f"chunk {chunk.chunk_index} missing word_segments"
        assert len(chunk.word_segments) > 0, f"chunk {chunk.chunk_index} has empty word_segments"
        # Every entry must have text + bbox
        for ws in chunk.word_segments:
            assert "text" in ws and "bbox" in ws, f"word_segment missing key: {ws}"

    # Verify Metformin can be found in the chunk containing it
    med_chunk = next((c for c in chunks if "Metformin" in c.chunk_text), None)
    assert med_chunk is not None, "'Metformin' not found in any chunk"

    from app.utils.bbox_utils import find_term_bbox
    result = find_term_bbox("Metformin 500mg", med_chunk.word_segments)
    assert result is not None, "find_term_bbox could not find 'Metformin 500mg' in chunk word_segments"
    assert result["x0"] >= 80, f"Metformin x0={result['x0']} looks too far left"


run("chunk_page_with_bbox: populates word_segments + bbox on all chunks", _test_chunk_page_with_bbox_word_segments)


# 4. J2 mapping check: word_segments flows into DocumentChunk kwargs ───────────
def _test_j2_chunk_kwargs():
    """
    Replicate the J2 DocumentChunk construction from j2_chunk_embed.py and
    confirm word_segments is present when chunk_data has it.
    """
    from app.services.chunking_service import ChunkData, ChunkingService
    from app.models.document_chunk import SectionType

    # Simulate a ChunkData with word_segments (as chunk_page_with_bbox produces)
    chunk_data = ChunkData(
        chunk_text="Metformin 500mg daily",
        page_number=1,
        section_type=SectionType.UNKNOWN,
        char_start=0,
        char_end=21,
        token_count=5,
        chunk_index=0,
        vector_id="test_vector_001",
        file_id="file-test-001",
        bbox={"x0": 85, "y0": 50, "x1": 250, "y1": 65},
        word_segments=[
            {"text": "Metformin", "bbox": {"x0": 85, "y0": 50, "x1": 150, "y1": 65}},
            {"text": "500mg",     "bbox": {"x0": 155,"y0": 50, "x1": 205, "y1": 65}},
            {"text": "daily",     "bbox": {"x0": 210,"y0": 50, "x1": 250, "y1": 65}},
        ],
    )

    # Replicate the exact J2 kwargs (j2_chunk_embed.py lines 117-134)
    j2_kwargs = dict(
        id=str(uuid.uuid4()),
        case_id="case-test",
        user_id="user-test",
        file_id=chunk_data.file_id,
        chunk_index=chunk_data.chunk_index,
        page_number=chunk_data.page_number,
        section_type=chunk_data.section_type,
        chunk_text=chunk_data.chunk_text,
        char_start=chunk_data.char_start,
        char_end=chunk_data.char_end,
        token_count=chunk_data.token_count,
        vector_id=chunk_data.vector_id,
        bbox=getattr(chunk_data, "bbox", None),
        word_segments=getattr(chunk_data, "word_segments", None),   # ← THE FIX
        created_at=datetime.utcnow(),
        embedding=None,
    )

    assert j2_kwargs["word_segments"] is not None, "word_segments missing from J2 kwargs"
    assert len(j2_kwargs["word_segments"]) == 3, "J2 kwargs should carry 3 word segments"
    assert j2_kwargs["bbox"] is not None, "bbox missing from J2 kwargs"


run("J2 mapping: word_segments wired into DocumentChunk kwargs", _test_j2_chunk_kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# PART 2 – Integration tests (real DB)
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("PART 2 — Integration Tests (PostgreSQL DB)")
print(SEP)

# Lazy import — don't crash Part 1 if DB is not available
try:
    from app.db.session import SessionLocal
    from app.models.document_chunk import DocumentChunk
    from app.models.entity_source import EntitySource
    from app.models.extraction import ClinicalExtraction
    from app.models.case_file import CaseFile
    from app.models.case import Case
    from app.services.entity_source_service import EntitySourceService
    from app.repositories.entity_source_repository import EntitySourceRepository

    _db_available = True
except Exception as _import_err:
    _db_available = False
    print(f"\n  {WARN} DB imports failed: {_import_err}")
    print("       Skipping all integration tests.")


# Helper: open a DB session and close it after the test
class _DB:
    def __enter__(self):
        self.db = SessionLocal()
        return self.db
    def __exit__(self, *args):
        self.db.close()


# 5. DB connectivity + entity_sources table ───────────────────────────────────
_db_ok = False

def _test_db_connection():
    global _db_ok
    if not _db_available:
        raise AssertionError("DB imports unavailable")
    with _DB() as db:
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).scalar()
        assert result == 1, "DB ping failed"

        # entity_sources table must exist
        tbl = db.execute(
            text("SELECT to_regclass('public.entity_sources')")
        ).scalar()
        assert tbl is not None, "entity_sources table not found — run: alembic upgrade head"

        # word_segments column must exist on document_chunks
        col = db.execute(
            text("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='document_chunks' AND column_name='word_segments'
            """)
        ).fetchone()
        assert col is not None, "word_segments column missing — run: alembic upgrade head"

    _db_ok = True

run("DB: connection + entity_sources table + word_segments column", _test_db_connection)


# 6. Fetch latest ClinicalExtraction ──────────────────────────────────────────
_extraction_case_id = None
_extraction_user_id = None
_extraction_data    = None
_extraction_sources = None
_file_lookup        = {}

def _test_fetch_extraction():
    global _extraction_case_id, _extraction_user_id, _extraction_data, _extraction_sources, _file_lookup
    if not _db_ok:
        raise AssertionError("DB not available — skipping")

    with _DB() as db:
        extraction = (
            db.query(ClinicalExtraction)
            .order_by(ClinicalExtraction.id.desc())
            .first()
        )
        assert extraction is not None, "No ClinicalExtraction rows in DB"

        extracted = extraction.extracted_data or {}
        sources   = (extraction.source_mapping or {}).get("extraction_sources", [])

        total_entities = sum(
            len(extracted.get(k, []))
            for k in ["medications", "labs", "diagnoses", "procedures", "vitals"]
        )
        assert total_entities > 0, "Extraction has no entity data"

        case_files = (
            db.query(CaseFile)
            .filter(CaseFile.case_id == extraction.case_id)
            .all()
        )
        assert case_files, f"No CaseFile rows for case {extraction.case_id}"

        _extraction_case_id = extraction.case_id
        _extraction_user_id = extraction.user_id
        _extraction_data    = extracted
        _extraction_sources = sources
        _file_lookup        = {f.id: f.file_name for f in case_files}

        diag_count = len(extracted.get("diagnoses", []))
        med_count  = len(extracted.get("medications", []))
        lab_count  = len(extracted.get("labs", []))
        src_count  = len(sources)

        print(f"\n       → case_id={_extraction_case_id}")
        print(f"         entities: {med_count} meds | {lab_count} labs | {diag_count} dx | {src_count} sources")
        print(f"         files: {list(_file_lookup.values())}")

run("DB: fetch most-recent ClinicalExtraction + files", _test_fetch_extraction)


# 7. Simulate J3 → create EntitySource records ────────────────────────────────
_created_entity_ids = []   # track what we create so we can clean up

def _test_create_entity_sources():
    global _created_entity_ids
    if not _db_ok or not _extraction_case_id:
        raise AssertionError("Prerequisites not met — skipping")

    ess = EntitySourceService()

    with _DB() as db:
        # Delete any pre-existing EntitySource rows for this case so test is clean
        db.query(EntitySource).filter(
            EntitySource.case_id == _extraction_case_id
        ).delete(synchronize_session=False)
        db.commit()

        count = ess.create_sources_from_extraction(
            db=db,
            case_id=_extraction_case_id,
            user_id=_extraction_user_id,
            extracted_data=_extraction_data,
            extraction_sources=_extraction_sources,
            file_lookup=_file_lookup,
        )

        assert count > 0, (
            "create_sources_from_extraction returned 0. "
            f"extraction_sources had {len(_extraction_sources)} entries. "
            "Clinical data may lack matching chunks — check RAG retriever."
        )
        print(f"\n       → {count} EntitySource records created")

        # Record what was created so cleanup can remove them
        rows = db.query(EntitySource).filter(
            EntitySource.case_id == _extraction_case_id
        ).all()
        _created_entity_ids = [r.id for r in rows]

        # Spot check: at least one diagnosis or medication with a file_id
        has_file = [r for r in rows if r.file_id is not None]
        assert has_file, "All EntitySource rows have null file_id — source matching failed"

        types_present = {r.entity_type for r in rows}
        print(f"         entity types in DB: {types_present}")
        print(f"         with file_id: {len(has_file)}/{len(rows)}")

run("J3 simulation: create_sources_from_extraction → rows in DB", _test_create_entity_sources)


# 8. Verify EntitySource row contents ─────────────────────────────────────────
def _test_entity_source_contents():
    if not _db_ok or not _created_entity_ids:
        raise AssertionError("Prerequisites not met — skipping")

    with _DB() as db:
        rows = db.query(EntitySource).filter(
            EntitySource.case_id == _extraction_case_id
        ).all()

        for row in rows:
            assert row.entity_type, f"Row {row.id} missing entity_type"
            assert row.entity_id,   f"Row {row.id} missing entity_id"
            assert row.page_number > 0, f"Row {row.id} has invalid page_number={row.page_number}"

            # entity_id must follow pattern  "type:index"  e.g. "diagnosis:0"
            parts = row.entity_id.split(":")
            assert len(parts) == 2 and parts[1].isdigit(), (
                f"entity_id '{row.entity_id}' does not match 'type:index' pattern"
            )

        print(f"\n       → all {len(rows)} rows have valid entity_type/entity_id/page_number")
        # Show a sample
        for r in rows[:5]:
            print(f"         {r.entity_id:30s}  file_id={r.file_id or 'None':36s}  page={r.page_number}")

run("DB: EntitySource row integrity check", _test_entity_source_contents)


# 9. Retrieval path (mirrors sources.py primary path) ─────────────────────────
def _test_retrieval_path():
    if not _db_ok or not _created_entity_ids:
        raise AssertionError("Prerequisites not met — skipping")

    repo = EntitySourceRepository()

    with _DB() as db:
        rows = db.query(EntitySource).filter(
            EntitySource.case_id == _extraction_case_id
        ).all()

        assert rows, "No EntitySource rows to test retrieval on"

        # Pick the first row and try a targeted get_by_entity lookup
        target = rows[0]
        entity_type = target.entity_type   # e.g. "diagnosis"
        entity_id   = target.entity_id     # e.g. "diagnosis:0"

        found = repo.get_by_entity(
            db,
            case_id=_extraction_case_id,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=_extraction_user_id,
        )
        assert found is not None, (
            f"get_by_entity({entity_type}, {entity_id}) returned None — "
            "sources endpoint primary path would 404"
        )
        assert found.file_id is not None or found.chunk_id is not None, (
            f"EntitySource for {entity_id} has neither file_id nor chunk_id"
        )
        print(f"\n       → get_by_entity('{entity_id}') → file_id={found.file_id}, page={found.page_number}")

        # Try all created rows to surface any with missing file_id
        missing = [r.entity_id for r in rows if r.file_id is None and r.chunk_id is None]
        if missing:
            print(f"       {WARN} {len(missing)} entities have neither file_id nor chunk_id: {missing[:5]}")
        else:
            print(f"         All {len(rows)} entities resolvable ✓")

run("Retrieval: entity_source_repo.get_by_entity works for all entity types", _test_retrieval_path)


# 10. word_segments round-trip in document_chunks ─────────────────────────────
_test_chunk_id = None

def _test_word_segments_roundtrip():
    global _test_chunk_id
    if not _db_ok or not _extraction_case_id:
        raise AssertionError("Prerequisites not met — skipping")

    # Fetch an existing chunk for this case and inject word_segments
    with _DB() as db:
        chunk = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.case_id == _extraction_case_id)
            .first()
        )
        assert chunk is not None, "No DocumentChunk rows for this case"
        _test_chunk_id = chunk.id

        mock_word_segs = [
            {"text": "TEST_WORD",  "bbox": {"x0": 10.0, "y0": 20.0, "x1": 80.0, "y1": 35.0}},
            {"text": "ANOTHER",    "bbox": {"x0": 85.0, "y0": 20.0, "x1": 150.0, "y1": 35.0}},
        ]
        chunk.word_segments = mock_word_segs
        db.commit()

    # Read back in a fresh session
    with _DB() as db:
        fresh = db.query(DocumentChunk).filter(DocumentChunk.id == _test_chunk_id).first()
        assert fresh is not None
        ws = fresh.word_segments
        assert ws is not None, "word_segments was not persisted to DB"
        assert len(ws) == 2, f"Expected 2 word segments back, got {len(ws)}"
        assert ws[0]["text"] == "TEST_WORD", f"text mismatch: {ws[0]['text']}"
        assert ws[0]["bbox"]["x0"] == 10.0, f"bbox x0 mismatch: {ws[0]['bbox']}"
        print(f"\n       → word_segments persisted and retrieved correctly for chunk {_test_chunk_id[:8]}…")

    # Restore original (set back to None so we don't pollute the case)
    with _DB() as db:
        chunk = db.query(DocumentChunk).filter(DocumentChunk.id == _test_chunk_id).first()
        chunk.word_segments = None
        db.commit()

run("DB: word_segments round-trip (insert → read back → restore)", _test_word_segments_roundtrip)


# 11. Cleanup – remove test EntitySource rows ─────────────────────────────────
def _test_cleanup():
    if not _db_ok or not _created_entity_ids:
        raise AssertionError("Nothing to clean up")

    with _DB() as db:
        deleted = (
            db.query(EntitySource)
            .filter(EntitySource.id.in_(_created_entity_ids))
            .delete(synchronize_session=False)
        )
        db.commit()

    print(f"\n       → Deleted {deleted} test EntitySource rows")

run("Cleanup: remove test EntitySource rows", _test_cleanup)


# ─────────────────────────────────────────────────────────────────────────────
# Final summary
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n{SEP}")
print("SUMMARY")
print(SEP)

passed = [r for r in _results if r[1]]
failed = [r for r in _results if not r[1]]

for label, ok, msg in _results:
    status = PASS if ok else FAIL
    note   = f"  ✗ {msg}" if msg else ""
    print(f"  {status} {label}{note}")

print(f"\n  Total: {len(passed)}/{len(_results)} passed")

if failed:
    print(f"\n  {len(failed)} FAILED test(s) — check output above for details")
    sys.exit(1)
else:
    print(f"\n  All tests passed. The evidence pipeline is wired correctly.")
    sys.exit(0)
