import asyncio
import os
import sys
import re
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, PatternRecognizer, Pattern
from presidio_analyzer.nlp_engine import NlpEngineProvider

# Mock or local copy of the recognizers to avoid DB imports
VALID_STATES = r"AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|MA|MD|ME|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY"

def get_analyzer():
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_trf"}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    nlp_engine = provider.create_engine()
    
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine)
    
    # Custom Patterns
    registry.add_recognizer(PatternRecognizer(supported_entity="MRN", patterns=[Pattern("MRN", r"\bMRN[:\s]*\d{4,12}\b", 0.95)]))
    registry.add_recognizer(PatternRecognizer(supported_entity="ID", patterns=[
        Pattern("ID Pattern", r"\b[A-Z]{2,4}-\d{4,15}\b", 0.95),
        Pattern("Dev ID Pattern", r"\bDEV-\d{4,10}\b", 0.95),
        Pattern("BF Pattern", r"\bBF-\d{4,15}\b", 0.95),
        Pattern("FaceScan Pattern", r"\b(?:FACESCAN|FACE)-\d{4,8}\b", 0.95),
        Pattern("BioToken Pattern", r"\b(?:BIO|RET|FP)-\d{4,12}\b", 0.95),
        Pattern("Medicare MBI", r"\b[1-9][A-Z][0-9A-Z][0-9]-[A-Z][0-9A-Z][0-9]-[A-Z]{2}[0-9]{2}\b", 0.99),
        Pattern("Prescription RX", r"\bRX-\d{4,10}\b", 0.95),
        Pattern("Internal Case ID", r"\bCASE-\d{4}-\d{5,10}\b", 0.95),
        Pattern("Lab Order", r"\bLAB-\d{4,10}\b", 0.95),
        Pattern("Sample ID", r"\bSMP-\d{4,10}\b", 0.95),
    ]))
    registry.add_recognizer(PatternRecognizer(supported_entity="STREET_ADDRESS", patterns=[
        Pattern("Street Address", r"\b\d{1,6}(?:st|nd|rd|th)?\s(?:[A-Z][a-z0-9#-]+\s){1,6}(?:Street|St|Avenue|Ave|Road|Rd|Blvd|Lane|Ln|Drive|Dr|Terrace|Way|Court|Ct|Circle|Cir|Place|Pl)\b", 0.99)
    ]))
    registry.add_recognizer(PatternRecognizer(supported_entity="ZIP_CODE", patterns=[Pattern("ZIP", r"\b\d{5}(?:-\d{4})?\b", 0.99)]))
    
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
