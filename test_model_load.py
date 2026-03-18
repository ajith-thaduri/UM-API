import os
from transformers import AutoTokenizer, AutoModelForTokenClassification

model_name = "StanfordAIMI/stanford-deidentifier-base"
print(f"Attempting to download/load {model_name}...")
try:
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForTokenClassification.from_pretrained(model_name)
    print("Successfully loaded model!")
except Exception as e:
    print(f"FAILED to load model: {e}")
