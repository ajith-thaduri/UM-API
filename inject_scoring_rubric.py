import os
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.db.session import SessionLocal
from app.repositories.prompt_repository import prompt_repository
import re

def update_prompts_for_JSON_confidence():
    db = SessionLocal()
    user_id = "00000000-0000-0000-0000-000000000000"
    
    scoring_logic = """

SUMMARY CONFIDENCE EVALUATION (MANDATORY JSON OUTPUT)
You must evaluate the quality of the provided medical record before writing the summary. 
Use the following strict scoring rubric to assess completeness, timeline continuity, and consistency.

RUBRIC:
- 90-100% (HIGH CONFIDENCE): Data is complete, largely chronological, and without major unresolvable contradictions. Minor gaps are acceptable.
- 70-89% (MEDIUM CONFIDENCE): Noticeable gaps exist (e.g., missing specific daily logs or isolated timeline skips) but the core narrative is reliable.
- <70% (LOW CONFIDENCE / FAILSAFE): CRITICAL missing data (e.g., unknown discharge disposition), unresolvable contradictions (e.g., conflicting dates of birth, conflicting primary diagnoses), or massive timeline gaps making it impossible to determine an accurate clinical course.

MANDATORY OUTPUT FORMAT:
You must return ONLY a structured JSON object containing your evaluation and the final summary. Do not include markdown code fences ```json around the response.

{
  "confidence_evaluation": {
    "overall_score": <int 0-100 based on the rubric>,
    "reason": "<A brief, 1-2 sentence explanation for the assigned score. Do not omit this. Be specific about missing or conflicting data if the score is <90.>"
  },
  "summary_markdown": "<Place your fully structured markdown summary here. Ensure it follows all structural and safety rules previously defined. Use newline characters properly.>"
}
"""

    try:
        def clean_prompt(text):
            # Remove previous instructions that explicitly prohibited JSON
            text = re.sub(r"OUTPUT ONLY HUMAN-READABLE MARKDOWN\. DO NOT USE JSON\.", "", text)
            text = re.sub(r"CRITICAL: DO NOT OUTPUT JSON\. PROVIDE ONLY HUMAN-READABLE MARKDOWN TEXT\. START DIRECTLY WITH THE SUMMARY CONTENT\.", "", text)
            return text

        for pid in ["summary_generation", "executive_summary_generation"]:
            p = prompt_repository.get_by_id(db, pid)
            if p:
                new_sys = clean_prompt(p.system_message)
                
                if "SUMMARY CONFIDENCE EVALUATION" not in new_sys:
                    new_sys += scoring_logic
                
                prompt_repository.update_prompt(
                    db=db, prompt_id=pid, template=p.template, system_message=new_sys,
                    user_id=user_id, change_notes="Enforcing JSON output and Confidence Scoring Evaluation."
                )
                print(f"Updated {pid}")
            else:
                print(f"Could not find {pid}")

        # Clear cache
        from app.services.prompt_service import prompt_service
        prompt_service.refresh_cache()
        print("Done.")

    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    update_prompts_for_JSON_confidence()
