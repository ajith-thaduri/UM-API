import re
text = "Patient Portal Username: daniel.mitchell82"
pattern = re.compile(r"\b(?:Username|User\s*ID|Login|Portal\s*Username)[:\s]+([a-zA-Z0-9._-]+)\b", re.IGNORECASE)
for match in pattern.finditer(text):
    print("Group 0:", text[match.start(0):match.end(0)])
    print("Group 1:", text[match.start(1):match.end(1)])
    start = match.start(1) if 1 else match.start()
    end = match.end(1) if 1 else match.end()
    print("Extracted:", text[start:end])
