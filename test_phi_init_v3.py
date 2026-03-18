import logging
import sys
import traceback
from presidio_analyzer.nlp_engine import NlpEngineProvider

logging.basicConfig(level=logging.INFO)

_STANFORD_MODEL = "StanfordAIMI/stanford-deidentifier-base"

nlp_config = {
    "nlp_engine_name": "transformers",
    "models": [{
        "lang_code": "en",
        "model_name": _STANFORD_MODEL,
    }],
}

print("Attempting to create NlpEngineProvider with simple model_name...")
try:
    provider = NlpEngineProvider(nlp_configuration=nlp_config)
    print("Creating engine...")
    engine = provider.create_engine()
    print("Engine created successfully!")
except Exception:
    print("FAILED to create engine!")
    traceback.print_exc()
