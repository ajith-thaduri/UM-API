import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.services.prompt_service import prompt_service

def verify_safety_rules():
    p1_id = "summary_generation"
    p2_id = "executive_summary_generation"
    
    rules_header = "STRICT DOCUMENTATION SAFETY RULES (MANDATORY)"
    
    # 1. Check summary_generation
    sys1 = prompt_service.get_system_message(p1_id)
    if rules_header in sys1:
        print(f"SUCCESS: Safety rules found in {p1_id} system message.")
    else:
        print(f"FAILURE: Safety rules NOT found in {p1_id} system message.")
        
    # 2. Check executive_summary_generation
    sys2 = prompt_service.get_system_message(p2_id)
    if rules_header in sys2:
        print(f"SUCCESS: Safety rules found in {p2_id} system message.")
    else:
        print(f"FAILURE: Safety rules NOT found in {p2_id} system message.")

if __name__ == "__main__":
    verify_safety_rules()
