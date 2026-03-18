"""
presidio/engine.py
━━━━━━━━━━━━━━━━━━
NLP engine initialisation, custom-recognizer registration,
and engine-switching / info methods.
"""

from typing import Any, Dict, Optional

from app.models.presidio_engine import PresidioEngine
from app.db.session import SessionLocal
from app.utils.safe_logger import get_safe_logger
from .constants import ROBERTA_LABEL_TO_PRESIDIO

try:
    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    PRESIDIO_AVAILABLE = True
except ImportError:
    PRESIDIO_AVAILABLE = False

safe_logger = get_safe_logger(__name__)

_STANFORD_MODEL = "StanfordAIMI/stanford-deidentifier-base"


class EngineManager:
    """Owns the Presidio AnalyzerEngine lifecycle."""

    def __init__(self, custom_recognizers: list):
        self.analyzer: Optional[Any] = None
        self.anonymizer: Optional[Any] = None
        self.active_ner_engine: str = "transformers"
        self.active_model_name: str = _STANFORD_MODEL
        self.active_engine_id: Optional[str] = None
        self._custom_recognizers = custom_recognizers

        if PRESIDIO_AVAILABLE:
            self.anonymizer = AnonymizerEngine()
            self._load_active_engine_from_db()
            safe_logger.info(
                f"EngineManager initialized: {self.active_ner_engine} ({self.active_model_name})"
            )

    # ── Initialisation ────────────────────────────────────────────────────────

    def _load_active_engine_from_db(self) -> None:
        """Load active engine from DB (audit only). Always enforces Stanford AIMI."""
        db = SessionLocal()
        try:
            active_engine = (
                db.query(PresidioEngine).filter(PresidioEngine.is_active == True).first()
            )
            if active_engine:
                self.active_engine_id = active_engine.id
                if (
                    active_engine.engine_type != "transformers"
                    or active_engine.model_name != _STANFORD_MODEL
                ):
                    safe_logger.warning(
                        f"DB active engine is '{active_engine.name}' "
                        f"({active_engine.model_name}), but Stanford AIMI is enforced."
                    )
            else:
                self.active_engine_id = None
                safe_logger.info("No active engine in DB — using Stanford AIMI (default).")

            self.active_ner_engine = "transformers"
            self.active_model_name = _STANFORD_MODEL
            self._init_transformers_engine()
            self._register_custom_recognizers()
        except Exception as e:
            safe_logger.error(f"Failed to initialize Stanford AIMI engine: {e}.")
            raise RuntimeError(f"Presidio Stanford AIMI engine failed to initialize: {e}") from e
        finally:
            db.close()

    def _init_transformers_engine(self) -> None:
        """Initialize Stanford AIMI HuggingFace transformers engine (only model used)."""
        nlp_config = {
            "nlp_engine_name": "transformers",
            "models": [{
                "lang_code": "en",
                "model_name": {
                    "spacy": "en_core_web_sm",
                    "transformers": _STANFORD_MODEL,
                },
                "labels_to_ignore": ["VENDOR", "PATORG", "HCW", "HOSP", "OTHERPHI"],
            }],
            "model_to_presidio_entity_mapping": ROBERTA_LABEL_TO_PRESIDIO,
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()
        self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        self.active_ner_engine = "transformers"
        self.active_model_name = _STANFORD_MODEL
        safe_logger.info(f"Transformers engine initialized: {_STANFORD_MODEL}")

    def _init_spacy_engine(self, model_name: str = "en_core_web_lg") -> None:
        """Initialize spaCy engine (not used for case processing)."""
        try:
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            }
            provider = NlpEngineProvider(nlp_configuration=nlp_config)
            nlp_engine = provider.create_engine()
            self.analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
            self.active_ner_engine = "spacy"
            self.active_model_name = model_name
            safe_logger.info(f"spaCy engine initialized: {model_name}")
        except SystemExit as e:
            safe_logger.error(f"spaCy model '{model_name}' raised SystemExit: {e}. Retrying with en_core_web_lg.")
            fallback = "en_core_web_lg"
            nlp_config = {"nlp_engine_name": "spacy", "models": [{"lang_code": "en", "model_name": fallback}]}
            provider = NlpEngineProvider(nlp_configuration=nlp_config)
            self.analyzer = AnalyzerEngine(nlp_engine=provider.create_engine())
            self.active_ner_engine = "spacy"
            self.active_model_name = fallback

    def _register_custom_recognizers(self) -> None:
        """Register all custom medical PHI recognizers."""
        if not self.analyzer:
            return
        registered_names = [
            getattr(r, "name", None) for r in self.analyzer.registry.recognizers
        ]
        for recognizer in self._custom_recognizers:
            name = getattr(recognizer, "name", None) or getattr(recognizer, "supported_entity", None)
            if name and name not in registered_names:
                self.analyzer.registry.add_recognizer(recognizer)
                registered_names.append(name)
                safe_logger.debug(f"Registered recognizer: {name}")
        safe_logger.info(f"Custom HIPAA recognizers registered: {len(self._custom_recognizers)}")

    # ── Engine switching & info (Presidio Lab / admin API) ────────────────────

    def switch_ner_engine(self, engine_type: str = None, model_id: str = None) -> Dict[str, Any]:
        """Switch the DB active-engine record (admin/lab only — case processing always uses Stanford AIMI)."""
        if not PRESIDIO_AVAILABLE:
            return {"status": "error", "message": "Presidio not available"}

        db = SessionLocal()
        try:
            target_engine = None
            if model_id:
                target_engine = db.query(PresidioEngine).filter(PresidioEngine.id == model_id).first()
                if not target_engine:
                    return {"status": "error", "message": f"Model ID {model_id} not found"}
            elif engine_type:
                target_engine = (
                    db.query(PresidioEngine).filter(PresidioEngine.engine_type == engine_type).first()
                )
                if not target_engine:
                    return {"status": "error", "message": f"No engine for type {engine_type}"}
            if not target_engine:
                return {"status": "error", "message": "No model specified"}

            db.query(PresidioEngine).update({PresidioEngine.is_active: False})
            target_engine.is_active = True
            db.commit()
            self._load_active_engine_from_db()

            return {
                "status": "success",
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
                "active_id": self.active_engine_id,
                "message": f"Switched to {target_engine.name}",
            }
        except Exception as e:
            db.rollback()
            safe_logger.error(f"Failed to switch engine: {e}")
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def get_engine_info(self) -> Dict[str, Any]:
        """Return current engine info and all available models from DB."""
        if not PRESIDIO_AVAILABLE:
            return {"status": "Presidio not available", "available_models": [], "active_engine": None}
        db = SessionLocal()
        try:
            available = db.query(PresidioEngine).all()
            return {
                "active_engine": self.active_ner_engine,
                "active_model": self.active_model_name,
                "active_id": self.active_engine_id,
                "available_models": [
                    {
                        "id": m.id, "name": m.name, "engine_type": m.engine_type,
                        "model_name": m.model_name, "description": m.description,
                        "is_active": m.is_active,
                    }
                    for m in available
                ],
                "presidio_available": PRESIDIO_AVAILABLE,
            }
        finally:
            db.close()
