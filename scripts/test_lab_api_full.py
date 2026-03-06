import requests
import json

text = """
Patient Name: Daniel Christopher Mitchell
Alias: Dan Mitchell
Gender: Male

Date of Birth: September 18, 1982
Age: 42

Social Security Number: 623-44-9182
Medical Record Number (MRN): MRN-88392011

Home Address:
4587 Pinecrest Drive
Apartment 12B
San Diego, California 92103

Phone Number: +1-619-555-7712
Email Address: daniel.mitchell82@gmail.com
Patient Portal Username: daniel.mitchell82

Employer: Pacific Finance Group
MAC Address: 00:1A:2B:3C:4D:5E

Appointment Time: 10:30 AM
"""

url = "http://127.0.0.1:8000/api/v1/presidio/analyze"
payload = {
    "text": text,
    "score_threshold": 0.35,
    "add_explanations": False
}

try:
    response = requests.post(url, json=payload)
    response.raise_for_status()
    data = response.json()
    
    print(f"Status Code: {response.status_code}")
    print("\n--- Detected Entities ---")
    for ent in data.get('entities', []):
        print(f"[{ent['entity_type']}] Conf: {ent['score']} | Text: '{ent['text']}' (Start: {ent['start']}, End: {ent['end']})")
    
    print("\n--- De-identified Text ---")
    print(data.get('de_identified_text'))
    
except Exception as e:
    print(f"Error: {e}")
    if 'response' in locals():
        print(response.text)
