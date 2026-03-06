import requests

text = """
The system detected only
https://hospitalrecords.com/photos/henry_matthews_1985.jpg.

Full portal URL
https://portal.greenvalleymed.org/users/henry.matthews85

Patient portal URL
https://portal.mercygeneral.org/patient/henrywalker
"""

url = "http://127.0.0.1:8000/api/v1/presidio/analyze"
payload = {"text": text, "score_threshold": 0.35}

try:
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    for ent in data.get('entities', []):
        print(f"[{ent['entity_type']}] Conf: {ent['score']} | {ent['text']}")
except Exception as e:
    print(f"Error: {e}")
