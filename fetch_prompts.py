import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_URL = "postgresql://utility:ZDqEnVyZVxSfGWALtZwEhMAmSZSP3gkN@dpg-d50fabggjchc73cbbmc0-a.oregon-postgres.render.com/um_v4"

def fetch_prompts():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        
        prompt_ids = ["summary_generation", "executive_summary_generation"]
        for p_id in prompt_ids:
            print(f"\n--- PROMPT: {p_id} ---")
            cur.execute("SELECT template, system_message FROM prompts WHERE id = %s", (p_id,))
            row = cur.fetchone()
            if row:
                template, system_message = row
                print(f"SYSTEM MESSAGE:\n{system_message}\n")
                print(f"TEMPLATE:\n{template}\n")
            else:
                print(f"Prompt {p_id} NOT FOUND")
        
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fetch_prompts()
