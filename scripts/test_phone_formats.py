import requests

text = """
Missing Phone Formats:

Direct: +1-512-555-7834
Dotted: 512.555.7834
Tel Link: tel:+15125557834
Standard: (512) 555-7834
"""

url = "http://127.0.0.1:8000/api/v1/presidio/analyze"
payload = {"text": text, "score_threshold": 0.35}

try:
    response = requests.post(url, json=payload, timeout=30)
    data = response.json()
    print("Detected Entities:")
    for ent in data.get('entities', []):
        text_frag = text[ent['start']:ent['end']]
        print(f"[{ent['entity_type']}] Conf: {ent['score']} | {text_frag}")
        
    print("\n--- De-identified Text ---")
    print(data.get('de_identified_text'))
    
except Exception as e:
    print(f"Error: {e}")
