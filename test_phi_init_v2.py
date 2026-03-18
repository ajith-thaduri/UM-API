import logging
import sys
import traceback
from presidio_analyzer.nlp_engine import NlpEngineProvider

logging.basicConfig(level=logging.INFO)

_STANFORD_MODEL = "StanfordAIMI/stanford-deidentifier-base"
_ROBERTA_LABEL_TO_PRESIDIO = {
    "PATIENT": "PERSON",
    "STAFF": "PERSON",
    "HCW": "PERSON",
    "AGE": "AGE",
    "DATE": "DATE_TIME",
    "PHONE": "PHONE_NUMBER",
    "EMAIL": "EMAIL_ADDRESS",
    "ID": "ID",
    "HOSP": "ORGANIZATION",
    "HOSPITAL": "ORGANIZATION",
    "VENDOR": "ORGANIZATION",
    "PATORG": "ORGANIZATION",
    "LOC": "LOCATION",
    "OTHERPHI": "NRP",
    "MAC_ADDRESS": "MAC_ADDRESS",
    "SUB_ADDRESS": "SUB_ADDRESS",
}

nlp_config = {
    "nlp_engine_name": "transformers",
    "models": [{
        "lang_code": "en",
        "model_name": {
            "spacy": "en_core_web_sm",
            "transformers": _STANFORD_MODEL,
        },
    }],
    "model_to_presidio_entity_mapping": _ROBERTA_LABEL_TO_PRESIDIO,
}

print("Attempting to create NlpEngineProvider...")
try:
    provider = NlpEngineProvider(nlp_configuration=nlp_config)
    print("Creating engine...")
    engine = provider.create_engine()
    print("Engine created successfully!")
except Exception:
    print("FAILED to create engine!")
    traceback.print_exc()
