import json
import re
import asyncio
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.services.llm.llm_factory import get_tier1_llm_service_for_user
from app.utils.safe_logger import get_safe_logger

safe_logger = get_safe_logger(__name__)

class AICorrectionService:
    """
    Uses a Tier-1 LLM to detect over-redacted phrases in de-identified text
    and suggests restorations for terms that are important for clinical context
    but were incorrectly flagged as PHI.
    """

    async def get_correction_suggestions(
        self, 
        db: Session, 
        user_id: str, 
        de_identified_payload: Dict[str, Any],
        token_map: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Analyze de-identified clinical data and identify over-redacted terms using batching and deep context.
        """
        if not token_map:
            return []

        try:
            llm = get_tier1_llm_service_for_user(db, user_id)
        except Exception as e:
            safe_logger.error(f"Failed to get Tier-1 LLM for AI Correction: {e}")
            return []
        
        # Flatten the payload to a text representation for the LLM
        if isinstance(de_identified_payload, str):
            text_to_analyze = de_identified_payload
        else:
            clinical_data = de_identified_payload.get("clinical_data", de_identified_payload)
            text_to_analyze = json.dumps(clinical_data, indent=2)

        # Batching parameters
        BATCH_SIZE = 30
        MAX_CONCURRENCY = 5
        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        
        # Split token_map into batches
        token_batches = [token_map[i:i + BATCH_SIZE] for i in range(0, len(token_map), BATCH_SIZE)]
        
        # Pre-calculate enriched mapping strings with context snippets
        # This handles repeated tokens (like multiple [[REDACTED]]) correctly.
        occurrence_tracker = {}
        batch_mapping_strs = []
        
        for batch in token_batches:
            lines = []
            for item in batch:
                token = str(item['token'])
                occ = occurrence_tracker.get(token, 0)
                context = self._get_context_snippet(text_to_analyze, token, occurrence=occ)
                occurrence_tracker[token] = occ + 1
                
                lines.append(
                    f"- {token}: \"{item['original']}\" (Type: {item['type']})\n"
                    f"  Context: \"...{context}...\""
                )
            batch_mapping_strs.append("\n".join(lines))

        safe_logger.info(f"Processing AI Correction in {len(token_batches)} batches (Total tokens: {len(token_map)})")

        tasks = [
            self._get_batch_suggestions(llm, batch_mapping_strs[i], batch, semaphore, i + 1, len(token_batches))
            for i, batch in enumerate(token_batches)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_suggestions = []
        for i, res in enumerate(results):
            if isinstance(res, list):
                all_suggestions.extend(res)
            elif isinstance(res, Exception):
                safe_logger.error(f"Batch {i+1} failed: {res}")
        
        # De-duplicate suggestions by token + original text to be safe
        seen_keys = set()
        unique_suggestions = []
        for s in all_suggestions:
            key = f"{s['token']}|{s['original']}"
            if key not in seen_keys:
                unique_suggestions.append(s)
                seen_keys.add(key)
                
        safe_logger.info(f"AI Correction total: {len(unique_suggestions)} restoration suggestions found across all batches")
        return unique_suggestions

    async def _get_batch_suggestions(
        self, 
        llm: Any, 
        mapping_str: str, 
        token_batch: List[Dict[str, Any]],
        semaphore: asyncio.Semaphore,
        batch_num: int,
        total_batches: int
    ) -> List[Dict[str, Any]]:
        """Processes a single batch of tokens for over-redaction analysis using structured decisions."""
        
        # 18 Safe Harbor PHI restricted entity types (programmatic guard - never restore)
        STRICT_PHI_TYPES = {
            "DATE_TIME", "PHONE_NUMBER", "EMAIL_ADDRESS", "US_SSN",
            "ID", "IP_ADDRESS", "MAC_ADDRESS", "LOCATION",
            "COORDINATE", "URL", "SUB_ADDRESS", "AGE"
        }

        async with semaphore:
            # Build the JSON entities input for the prompt
            entities_json = []
            for idx, item in enumerate(token_batch):
                entities_json.append({
                    "id": idx + 1,
                    "token": item["token"],
                    "original": item["original"],
                    "type": item.get("type", "UNKNOWN"),
                    "context": mapping_str.split("\n")[idx] if idx < len(mapping_str.split("\n")) else ""
                })

            system_prompt = (
                "You are a HIPAA-aware clinical redaction auditor.\n\n"
                "TASK:\n"
                "Review entities and detect:\n"
                "1) OVER-REDACTION → non-PHI parts wrongly redacted\n"
                "2) MISCLASSIFICATION → wrong entity type assigned\n"
                "3) PARTIAL REDACTION → mixed text where non-PHI label should be restored but PHI must stay redacted\n\n"
                "STRICT RULES:\n"
                "- Never unredact real PHI: names, IDs, SSNs, locations, dates, contacts, ages, IP/MAC addresses, URLs\n"
                "- If text contains both PHI and non-PHI → only restore the non-PHI part using PARTIAL\n"
                "- Be conservative: if unsure → KEEP\n"
                "- Do not explain anything\n"
                "- Output only valid JSON\n"
                "- You must be deterministic: for the same input entities, always return the exact same decisions. Do not vary your output.\n\n"
                "SPECIFIC RULES FOR ENTITY TYPES:\n"
                "- USERNAMES (patient-linked): Any username or portal handle tied to a patient (e.g., 'jon_reynolds81') is PHI → KEEP.\n"
                "- USERNAMES (hyphenated descriptors): Hyphenated clinical adjectives mislabeled as USERNAME (e.g., 'year-old', 'long-term', 'well-controlled') are NOT PHI → UNREDACT.\n"
                "- ORGANIZATIONS labeled as ORGANIZATION: Specific named hospitals or employers → KEEP. Generic department names (Emergency Department, ICU, Lab) → UNREDACT.\n"
                "- ORGANIZATIONS labeled as PERSON: If a company/org name is mislabeled as PERSON (e.g., 'Amazon Health Services') → CHANGE_TYPE:ORGANIZATION.\n"
                "- TITLES/ROLES WITH PHI: If a role title like 'Radiologist', 'Nurse', 'Doctor' (or a multi-word sequence like 'Doctor Unique') appears alongside a PHI name, use PARTIAL to restore the entire title/descriptor portion.\n"
                "- ADDRESSES labeled as PERSON: A street address mislabeled as PERSON → CHANGE_TYPE:LOCATION.\n"
                "- LABELS WITH PHI: If a generic field label (e.g., 'patient', 'gender', 'born on', 'alias', 'Employer:') occurs in the same redacted span as a PHI value, use PARTIAL to restore ONLY the label.\n"
                "- RELATIONSHIPS: Terms describing family or social status (e.g., 'wife', 'husband', 'mother', 'is his wife') are context, not PHI → UNREDACT (or PARTIAL if attached to a name).\n"
                "- CONNECTORS WITH PHI: Prepositions or conjunctions starting a redacted block (e.g., 'at', 'on', 'in', 'near') are safe context. Use PARTIAL to extract them.\n"
                "- FULLY GENERIC SPANS: If the entire entity text is only generic labels, roles, or descriptors with NO actual PHI name present (e.g., 'doctor information doctor'), UNREDACT the entire span.\n"
                "- CLINICAL FRAGMENTS: Medical terms, symptoms, or partial text fragments (e.g., 'swelling, or', 'shortness of breath') are never PHI, regardless of punctuation → UNREDACT.\n\n"
                "DECISIONS:\n"
                "For each entity return ONE of:\n"
                "- KEEP → correct redaction, PHI confirmed\n"
                "- UNREDACT → fully safe non-PHI (e.g., clinical terms, generic headings, titles like MD/RN)\n"
                "- CHANGE_TYPE:<NEW_TYPE> → correct the entity type label (e.g., CHANGE_TYPE:ORGANIZATION)\n"
                "- PARTIAL:<SAFE_TEXT> → restore only the non-PHI label part, keep PHI redacted\n"
                "- REVIEW → uncertain, needs human review\n\n"
                "EXAMPLES:\n"
                "  'Patient Account' labeled as PERSON → UNREDACT\n"
                "  'Lab Report' labeled as PERSON → UNREDACT\n"
                "  'doctor information doctor' labeled as PERSON → UNREDACT (entirely generic labels)\n"
                "  'is his wife' labeled as PERSON → UNREDACT (relationship term)\n"
                "  'Doctor Notes Phyllis' labeled as PERSON → PARTIAL:Doctor Notes\n"
                "  'Sandra Rodriguez Doctor Unique' labeled as PERSON → PARTIAL:Doctor Unique\n"
                "  'Sarah Collins Radiologist' labeled as PERSON → PARTIAL:Radiologist\n"
                "  'John Doe gender' labeled as PERSON → PARTIAL:gender\n"
                "  'patient John Doe' labeled as PERSON → PARTIAL:patient\n"
                "  'John Doe born on' labeled as PERSON → PARTIAL:born on\n"
                "  'John Doe alias' labeled as PERSON → PARTIAL:alias\n"
                "  'at 4587 Pinecrest Drive' labeled as LOCATION → PARTIAL:at\n"
                "  '410 Terry Ave N' labeled as PERSON → CHANGE_TYPE:LOCATION\n"
                "  'Amazon Health Services' labeled as PERSON → CHANGE_TYPE:ORGANIZATION\n"
                "  'Employer: TechNova Solutions' labeled as ORGANIZATION → PARTIAL:Employer:\n"
                "  'Dr. Michael Thompson' → KEEP (full name is PHI)\n"
                "  'swelling, or' labeled as PERSON → UNREDACT (clinical symptom fragment)\n"
                "  'year-old' labeled as USERNAME → UNREDACT\n"
                "  'jon_reynolds81' labeled as USERNAME → KEEP\n"
                "  'Austin, TX' → KEEP (location)\n"
                "  'jonathan' → KEEP (name)\n\n"
                "OUTPUT FORMAT (strict JSON array, one entry per input entity):\n"
                "[\n"
                "  {\"id\": 1, \"decision\": \"KEEP\"},\n"
                "  {\"id\": 2, \"decision\": \"UNREDACT\"},\n"
                "  {\"id\": 3, \"decision\": \"CHANGE_TYPE:ORGANIZATION\"},\n"
                "  {\"id\": 4, \"decision\": \"PARTIAL:Doctor Notes\"},\n"
                "  {\"id\": 5, \"decision\": \"REVIEW\"}\n"
                "]"
            )

            user_prompt = (
                f"INPUT:\n{json.dumps(entities_json, indent=2)}"
            )

            try:
                # Low temperature and fixed seed for deterministic results
                response_text, _ = await llm.chat_completion(
                    messages=[{"role": "user", "content": user_prompt}],
                    system_message=system_prompt,
                    temperature=0.0,
                    seed=42
                )

                # Parse the JSON response
                decisions = []
                try:
                    match = re.search(r"(\[.*\])", response_text, re.DOTALL)
                    if match:
                        decisions = json.loads(match.group(1))
                    else:
                        decisions = json.loads(response_text.strip())
                except Exception:
                    safe_logger.warning(f"AI Correction batch {batch_num}: failed to parse LLM JSON response")
                    return []

                if not isinstance(decisions, list):
                    return []

                # Build a lookup from index to token item
                id_to_item = {idx + 1: item for idx, item in enumerate(token_batch)}

                valid_suggestions = []
                for d in decisions:
                    if not isinstance(d, dict):
                        continue
                    entity_id = d.get("id")
                    decision = str(d.get("decision", "")).strip()
                    
                    if not entity_id or not decision:
                        continue

                    item = id_to_item.get(entity_id)
                    if not item:
                        continue

                    token_str = str(item["token"])
                    entity_type = item.get("type", "")
                    original = str(item["original"])

                    # Programmatic guard: never restore strict Safe Harbor types
                    if entity_type in STRICT_PHI_TYPES:
                        safe_logger.info(f"AI Correction blocked strict PHI: {token_str} ({entity_type})")
                        continue

                    if decision == "KEEP" or decision == "REVIEW":
                        continue  # Leave redacted

                    elif decision == "UNREDACT":
                        valid_suggestions.append({
                            "token": token_str,
                            "original": original,
                            "reason": "Over-redaction: non-PHI term"
                        })

                    elif decision.startswith("CHANGE_TYPE:"):
                        new_type = decision.split(":", 1)[1].strip()
                        valid_suggestions.append({
                            "token": token_str,
                            "original": original,
                            "reason": f"Misclassification: should be {new_type}, not {entity_type}"
                        })

                    elif decision.startswith("PARTIAL:"):
                        safe_part = decision.split(":", 1)[1].strip()
                        if safe_part:
                            valid_suggestions.append({
                                "token": token_str,
                                "original": safe_part,  # Only the safe portion
                                "reason": f"Partial over-redaction: '{safe_part}' is non-PHI but surrounding text may contain PHI"
                            })

                return valid_suggestions

            except Exception as e:
                safe_logger.error(f"AI Correction batch {batch_num} failed: {e}")
                return []

    def _get_context_snippet(self, text: str, token: str, window: int = 70, occurrence: int = 0) -> str:
        """Extracts the specific occurrence of a token's surrounding context."""
        try:
            quoted_token = re.escape(token)
            matches = list(re.finditer(quoted_token, text))
            if not matches:
                return "Context not found"
            
            # If we asked for an occurrence that doesn't exist, fall back to first
            match = matches[occurrence] if occurrence < len(matches) else matches[0]
            
            start = max(0, match.start() - window)
            end = min(len(text), match.end() + window)
            
            snippet = text[start:end].replace("\n", " ")
            snippet = snippet.replace('"', "'")
            return snippet.strip()
        except:
            return "Snippet error"

ai_correction_service = AICorrectionService()
