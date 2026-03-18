import asyncio
import os
import sys
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Setup path for imports
sys.path.insert(0, os.path.join(os.getcwd()))

from app.services.presidio.recognizers import ALL_RECOGNIZERS
from app.services.presidio.constants import normalize_entity_type

def get_analyzer():
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_trf"}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    for rec in ALL_RECOGNIZERS:
        registry.add_recognizer(rec)
        
    return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry, default_score_threshold=0.4)

async def debug_detect():
    text = """Kevin Alexander Carter, a 42-year-old patient, was admitted to Green Valley Medical Center on January 18, 2024, for evaluation of chest pain and dizziness. Kevin was born on July 22, 1981, and currently resides at 4587 Pinecrest Drive, Apartment 12B, Austin, Texas 78704.

Kevin’s Social Security Number is 612-45-9087, and his hospital Medical Record Number (MRN) is MRN-87456321. His insurance policy number is INS-453829102, provided by BlueCross BlueShield. Kevin’s driver’s license number is TX-DL-78293451.

The patient can be contacted via his mobile phone at +1 (512) 555-7834 or through his email kevin.carter1981@gmail.com. His emergency contact is his wife, Laura Carter, reachable at 512-555-9812.

Kevin works as a senior financial analyst at Carter & Fields Consulting located at 1200 Congress Avenue, Suite 450, Austin, TX. His employee ID at the company is EMP-009874.

During the hospital visit, Kevin’s biometric identifiers were recorded, including fingerprint scan ID FP-778219 and facial recognition ID FACE-21984. A retinal scan reference RET-99821 was also stored in the hospital system.

Kevin’s health insurance member ID is BCBS-88902134, and his Medicare number is 5EG4-TE5-MK73. His prescription ID is RX-6637281.

The attending physician, Dr. Michael Thompson, documented the patient’s case and assigned internal case ID CASE-2024-09123.

Kevin previously visited Sunrise Diagnostic Laboratory at 3301 West 5th Street, Austin, TX, where his laboratory accession number LAB-778234 was generated.

Kevin also registered on the hospital portal using the username kevin.carter81 and the IP address 192.168.14.72 during the login session on 01/18/2024 at 09:43 AM.

For telehealth follow-up, Kevin scheduled an online appointment through https://greenvalleymedical.org/patientportal using device ID DEV-552819 and MAC address 00:1A:2B:3C:4D:5E."""

    analyzer = get_analyzer()
    results = analyzer.analyze(text=text, language="en", score_threshold=0.4)
    
    print(f"\nTotal Findings: {len(results)}")
    print(f"{'#':<3} {'Entity Type':<20} {'Text':<35} {'Start':<6} {'End':<6} {'Score':<6}")
    print("-" * 85)
    
    for i, res in enumerate(sorted(results, key=lambda x: x.start), 1):
        entity_text = text[res.start:res.end].replace('\n', ' ')
        print(f"{i:<3} {res.entity_type:<20} {entity_text:<35} {res.start:<6} {res.end:<6} {res.score:<6.2f}")

if __name__ == "__main__":
    asyncio.run(debug_detect())
