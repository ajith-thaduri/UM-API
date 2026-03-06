import requests

text = """
Patient Name: Daniel Christopher Mitchell
Alias: Dan Mitchell
Gender: Male

Patient Portal Username: daniel.mitchell82
MAC Address: 00:1A:2B:3C:4D:5E

Apartment 12B
Employer: Pacific Finance Group
"""
url = "http://127.0.0.1:8000/api/v1/presidio/analyze"
payload = {"text": text}
response = requests.post(url, json=payload)
data = response.json()
print(f"Status Code: {response.status_code}")
for ent in data.get('entities', []):
    print(f"{ent['entity_type']}: {ent['text']}")
