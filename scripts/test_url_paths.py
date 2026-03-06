import re

text = """
The system detected only
https://hospitalrecords.com/photos/henry_matthews_1985.jpg.

Full portal URL
https://portal.greenvalleymed.org/users/henry.matthews85

Patient portal URL
https://portal.mercygeneral.org/patient/henrywalker
"""

pattern1 = r"\b(?:https?://|www[:.]?)[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._?=&%-]*)?\b"
pattern2 = r"\b(?:https?://|www[:.]?)[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._?=&%/-]*)?" # without \b at the end for testing, or with \b

for m in re.finditer(pattern1, text):
    print("Old:", m.group(0))

for m in re.finditer(r"\b(?:https?://|www[:.]?)[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._?=&%/-]*)\b", text):
    print("New:", m.group(0))

