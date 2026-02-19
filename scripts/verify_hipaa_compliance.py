import sys
import os

# Set up environment
sys.path.append(os.getcwd())
os.environ["PRESIDIO_NER_MODEL"] = "en_core_web_lg" # Use lg for standard test

from app.services.presidio_deidentification_service import PresidioDeIdentificationService

def test_hipaa_compliance():
    service = PresidioDeIdentificationService()
    
    # Text with all the leaks identified by the user
    text = """
    Patient Name: David Williams
    MRN: 458921
    Hospital: Apollo Hospital
    Location: Apollo Hospital, Hyderabad
    Date: 12 January 2025
    Time: 08:45 AM
    DOB: 14 March 1972
    Doctor: Dr. Peter Siddle examined the patient at 09:00 AM.
    The patient was admitted to the Medical Center at 10:15 AM.
    Follow-up scheduled at 11:30 AM in Dallas, TX.
    """
    
    print("\n--- Original Text ---")
    print(text)
    
    # Simulate the service de-identification
    token_map = {}
    
    # In the real service, this is called during _process_single_string
    # We'll just run analyze directly to see what it finds
    results = service.analyzer.analyze(text=text, language='en', score_threshold=0.3)
    
    print("\n--- Detection Results ---")
    for res in sorted(results, key=lambda x: x.start):
        print(f"[{res.start}:{res.end}] Entity: {res.entity_type:<20} | Text: '{text[res.start:res.end].replace('\n', '\\n'):<25}' | Score: {res.score:.2f}")

    # Now run the actual de-identification logic
    # We'll use a mock object to simulate the structure PresidioDeIdentificationService expects
    parent = {"text": text}
    service._process_single_string(parent, "text", text, token_map)
    
    print("\n--- De-identified Text ---")
    print(parent["text"])
    
    # Check for specific leak removals
    leaks = ["Williams", "458921", "Apollo", "Hyderabad", "08:45", "1972", "Peter Siddle"]
    all_fixed = True
    print("\n--- Leak Check ---")
    for leak in leaks:
        if leak.lower() in parent["text"].lower():
            print(f"❌ LEAK STILL PRESENT: {leak}")
            all_fixed = False
        else:
            print(f"✅ FIXED: {leak} removed")
            
    if all_fixed:
        print("\n🏆 COMPLIANCE ACHIEVED: All identified leaks were tokenized!")
    else:
        print("\n⚠️ COMPLIANCE FAILED: Some leaks remain.")

if __name__ == "__main__":
    test_hipaa_compliance()
