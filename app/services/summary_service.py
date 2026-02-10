"""Summary generation service using structured data"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session
import logging

from app.core.config import settings
from app.models.document_chunk import SectionType
from app.services.llm.llm_factory import get_llm_service_instance
from app.services.prompt_service import prompt_service

logger = logging.getLogger(__name__)


class SummaryService:
    """Service for generating UM-ready summaries using structured data only"""

    def __init__(self):
        # Don't cache - get fresh service each time to pick up config changes
        pass
    
    def _get_llm_service(self, db: Optional[Session] = None, user_id: Optional[str] = None):
        """Get LLM service instance (fresh each time to respect config changes)"""
        if db and user_id:
            from app.services.llm.llm_factory import get_llm_service_for_user
            return get_llm_service_for_user(db, user_id)
        return get_llm_service_instance()
    
    def _get_model_name(self):
        """Get model name based on current provider config"""
        if settings.LLM_PROVIDER.lower() == "claude":
            return settings.CLAUDE_MODEL
        else:
            return settings.OPENAI_MODEL

    async def generate_summary(
        self,
        extracted_data: Dict,
        timeline: List[Dict],
        contradictions: List[Dict],
        patient_name: str,
        case_number: str,
        db: Optional[Session] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Generate UM-ready 1-2 page summary using structured data only
        
        Uses extracted_data, timeline, and contradictions for summary generation.
        No longer uses RAG for narrative context (removed for speed optimization).

        Args:
            extracted_data: Extracted clinical information
            timeline: Clinical timeline
            contradictions: Detected contradictions
            patient_name: Patient name
            case_number: Case number
            db: Database session
            case_id: Case ID
            user_id: User ID

        Returns:
            Formatted summary text
        """

        llm_service = self._get_llm_service(db, user_id)
        
        if not llm_service.is_available():
            return self._generate_mock_summary(
                extracted_data, timeline, contradictions, patient_name, case_number
            )

        # Prepare variables for the prompt
        diagnoses = extracted_data.get('diagnoses', [])
        diagnoses_text = []
        for dx in diagnoses:
            if isinstance(dx, str):
                diagnoses_text.append(dx)
            elif isinstance(dx, dict):
                name = dx.get('name', '')
                if name:
                    diagnoses_text.append(name)
        diagnoses_str = ', '.join(diagnoses_text) if diagnoses_text else 'Not explicitly documented'
        
        meds = extracted_data.get('medications', [])
        meds_summary = []
        for med in meds:
            name = med.get('name', 'Unknown')
            dosage = med.get('dosage', '')
            freq = med.get('frequency', '')
            meds_summary.append(f"- {name} {dosage} {freq}".strip())
        meds_text = '\n'.join(meds_summary) if meds_summary else 'Not explicitly documented'
        
        labs = extracted_data.get('labs', [])
        abnormal_labs = [lab for lab in labs if lab.get('abnormal')]
        labs_summary = []
        for lab in abnormal_labs:
            name = lab.get('test_name', 'Unknown')
            value = lab.get('value', '')
            unit = lab.get('unit', '')
            labs_summary.append(f"- {name}: {value} {unit} (ABNORMAL)")
        labs_text = '\n'.join(labs_summary) if labs_summary else 'No abnormal labs'
        
        procedures = extracted_data.get('procedures', [])
        procedures_summary = []
        for proc in procedures:
            name = proc.get('name', '') if isinstance(proc, dict) else str(proc)
            if name:
                date = proc.get('date', '') if isinstance(proc, dict) else ''
                if date:
                    procedures_summary.append(f"- {name} (Date: {date})")
                else:
                    procedures_summary.append(f"- {name}")
        procedures_text = '\n'.join(procedures_summary) if procedures_summary else 'Not explicitly documented'
        
        vitals = extracted_data.get('vitals', [])
        vitals_summary = []
        for vital in vitals[:10]:
            if isinstance(vital, dict):
                vital_type = vital.get('type', '')
                value = vital.get('value', '')
                unit = vital.get('unit', '')
                date = vital.get('date', '')
                if vital_type and value:
                    if date:
                        vitals_summary.append(f"- {vital_type}: {value} {unit} (Date: {date})")
                    else:
                        vitals_summary.append(f"- {vital_type}: {value} {unit}")
        vitals_text = '\n'.join(vitals_summary) if vitals_summary else 'Not explicitly documented'

        prompt_id = "summary_generation"
        variables = {
            "patient_name": patient_name,
            "case_number": case_number,
            "diagnoses_str": diagnoses_str,
            "meds_text": meds_text,
            "allergies_text": self._format_allergies_for_prompt(extracted_data.get('allergies', [])),
            "procedures_text": procedures_text,
            "labs_text": labs_text,
            "vitals_text": vitals_text,
            "timeline_text": self._format_timeline_for_prompt(timeline),
            "contradictions_text": self._format_contradictions_for_prompt(contradictions),
            "diagnoses_count": len(diagnoses),
            "meds_count": len(meds),
            "procedures_count": len(procedures),
            "labs_total_count": len(labs),
            "labs_abnormal_count": len(abnormal_labs),
            "timeline_count": len(timeline)
        }

        prompt = prompt_service.render_prompt(prompt_id, variables)
        system_message = prompt_service.get_system_message(prompt_id)

        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")

        try:
            # Determine provider for proper handling
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            from app.services.llm_utils import EXTRACTION_RULES
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # Add provider-specific guidance and centralized extraction rules
            if is_claude:
                prompt += "\n\nPROVIDER-SPECIFIC GUIDANCE: Aim for 2500-3500 tokens total. Be comprehensive but concise. Focus on completeness while maintaining readability."
                max_tokens = 6000  # Reduced from 16000 for alignment
            elif is_openai:
                prompt += "\n\nPROVIDER-SPECIFIC GUIDANCE: Aim for 2000-3000 tokens total. Be comprehensive but concise. Include all key clinical data while maintaining clarity."
                max_tokens = 6000  # Aligned with Claude
            else:
                max_tokens = 6000  # Default fallback
            
            prompt_with_rules = prompt + EXTRACTION_RULES
            
            response, usage = await llm_service.chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt_with_rules
                    }
                ],
                system_message=system_message,
                temperature=0.1,
                max_tokens=max_tokens
            )

            # Track usage if user_id is available
            if user_id and db:
                try:
                    from app.services.usage_tracking_service import usage_tracking_service
                    if is_claude:
                        provider_name = "claude"
                        model_name = getattr(llm_service, 'model', settings.CLAUDE_MODEL)
                    elif is_openai:
                        provider_name = "openai"
                        model_name = getattr(llm_service, 'model', settings.OPENAI_MODEL)
                    else:
                        provider_name = settings.LLM_PROVIDER.lower()
                        model_name = settings.LLM_MODEL
                    
                    usage_tracking_service.track_llm_usage(
                        db=db,
                        user_id=user_id,
                        provider=provider_name,
                        model=model_name,
                        operation_type="summary",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": "summary_generation",
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)

            return response

        except Exception as e:
            logger.error(f"Summary generation error: {e}", exc_info=True)
            return self._generate_mock_summary(
                extracted_data, timeline, contradictions, patient_name, case_number
            )

    async def generate_executive_summary(
        self,
        extracted_data: Dict,
        timeline: List[Dict],
        contradictions: List[Dict],
        patient_name: str,
        case_number: str,
        db: Optional[Session] = None,
        case_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> str:
        """
        Generate concise executive summary (5-10 bullet points) for PDFs and quick reference
        
        Args:
            extracted_data: Extracted clinical information
            timeline: Clinical timeline
            contradictions: Detected contradictions
            patient_name: Patient name
            case_number: Case number
            db: Database session
            case_id: Case ID
            user_id: User ID

        Returns:
            Executive summary as 5-10 bullet points
        """
        llm_service = self._get_llm_service(db, user_id)
        
        if not llm_service.is_available():
            return self._generate_mock_executive_summary(
                extracted_data, timeline, contradictions, patient_name, case_number
            )

        # Extract key data for executive summary
        key_data = self._extract_key_data_for_executive(extracted_data, timeline, contradictions)
        
        prompt_id = "executive_summary_generation"
        variables = {
            "patient_name": patient_name,
            "case_number": case_number,
            "admission_discharge_info": key_data['admission_discharge_info'],
            "primary_diagnoses": key_data['primary_diagnoses'],
            "key_medications": key_data['key_medications'],
            "critical_labs": key_data['critical_labs'],
            "key_events": key_data['key_events'],
            "concerns": key_data['concerns']
        }

        prompt = prompt_service.render_prompt(prompt_id, variables)
        system_message = prompt_service.get_system_message(prompt_id)

        if not system_message:
            logger.error(f"System message not found for prompt_id: {prompt_id}")
            raise ValueError(f"System message not found for prompt_id: {prompt_id}. Please ensure the prompt exists in the database.")

        try:
            # Determine provider for proper handling
            from app.services.llm.claude_service import ClaudeService
            from app.services.llm.openai_service import OpenAIService
            from app.services.llm_utils import EXTRACTION_RULES
            is_claude = isinstance(llm_service, ClaudeService)
            is_openai = isinstance(llm_service, OpenAIService)
            
            # Executive summary should be descriptive narrative - increased for 8-12 detailed bullets
            max_tokens = 2000  # Enough for 8-12 narrative bullets with clinical detail
            
            prompt_with_rules = prompt + EXTRACTION_RULES
            
            response, usage = await llm_service.chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt_with_rules
                    }
                ],
                system_message=system_message,
                temperature=0.1,
                max_tokens=max_tokens
            )

            # Track usage if user_id is available
            if user_id and db:
                try:
                    from app.services.usage_tracking_service import usage_tracking_service
                    if is_claude:
                        provider_name = "claude"
                        model_name = getattr(llm_service, 'model', settings.CLAUDE_MODEL)
                    elif is_openai:
                        provider_name = "openai"
                        model_name = getattr(llm_service, 'model', settings.OPENAI_MODEL)
                    else:
                        provider_name = settings.LLM_PROVIDER.lower()
                        model_name = settings.LLM_MODEL
                    
                    usage_tracking_service.track_llm_usage(
                        db=db,
                        user_id=user_id,
                        provider=provider_name,
                        model=model_name,
                        operation_type="summary",
                        prompt_tokens=usage.get("prompt_tokens", 0),
                        completion_tokens=usage.get("completion_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0),
                        case_id=case_id,
                        extra_metadata={
                            "operation": "executive_summary_generation",
                            "prompt_id": prompt_id
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to track usage: {e}", exc_info=True)

            return response

        except Exception as e:
            logger.error(f"Executive summary generation error: {e}", exc_info=True)
            return self._generate_mock_executive_summary(
                extracted_data, timeline, contradictions, patient_name, case_number
            )

    def _extract_key_data_for_executive(
        self, 
        extracted_data: Dict, 
        timeline: List[Dict],
        contradictions: List[Dict]
    ) -> Dict:
        """Extract key data points for executive summary"""
        
        # Admission/discharge info from timeline
        admission_events = [e for e in timeline if 'admission' in e.get('description', '').lower() or e.get('event_type', '').lower() == 'admission']
        discharge_events = [e for e in timeline if 'discharge' in e.get('description', '').lower() or e.get('event_type', '').lower() == 'discharge']
        
        admission_date = admission_events[0].get('date', 'Unknown') if admission_events else 'Not documented'
        discharge_date = discharge_events[0].get('date', 'Unknown') if discharge_events else 'Not documented'
        
        admission_discharge_info = f"Admission: {admission_date}, Discharge: {discharge_date}"
        
        # Primary diagnoses (top 3)
        diagnoses = extracted_data.get('diagnoses', [])
        primary_diagnoses_list = []
        for dx in diagnoses[:3]:
            if isinstance(dx, str):
                primary_diagnoses_list.append(dx)
            elif isinstance(dx, dict):
                name = dx.get('name', '')
                if name:
                    primary_diagnoses_list.append(name)
        primary_diagnoses = ', '.join(primary_diagnoses_list) if primary_diagnoses_list else 'Not documented'
        
        # Key medications (top 5)
        meds = extracted_data.get('medications', [])
        key_meds_list = []
        for med in meds[:5]:
            name = med.get('name', '')
            if name:
                dosage = med.get('dosage', '')
                key_meds_list.append(f"{name} {dosage}".strip())
        key_medications = ', '.join(key_meds_list) if key_meds_list else 'Not documented'
        
        # Critical lab findings (abnormals only, top 5)
        labs = extracted_data.get('labs', [])
        abnormal_labs = [lab for lab in labs if lab.get('abnormal')][:5]
        critical_labs_list = []
        for lab in abnormal_labs:
            name = lab.get('test_name', '')
            value = lab.get('value', '')
            unit = lab.get('unit', '')
            if name and value:
                critical_labs_list.append(f"{name} {value}{' ' + unit if unit else ''}")
        critical_labs = ', '.join(critical_labs_list) if critical_labs_list else 'No critical abnormals'
        
        # Key events (top 5 significant events)
        key_events_list = []
        for event in timeline[:5]:
            date = event.get('date', '')
            desc = event.get('description', '')
            if desc:
                key_events_list.append(f"{date}: {desc}")
        key_events = '\n'.join(key_events_list) if key_events_list else 'No significant events'
        
        # Concerns from contradictions
        concerns_list = []
        for c in contradictions[:3]:
            desc = c.get('description', '')
            if desc:
                concerns_list.append(desc)
        concerns = ', '.join(concerns_list) if concerns_list else 'None identified'
        
        return {
            'admission_discharge_info': admission_discharge_info,
            'primary_diagnoses': primary_diagnoses,
            'key_medications': key_medications,
            'critical_labs': critical_labs,
            'key_events': key_events,
            'concerns': concerns
        }

    def _generate_mock_executive_summary(
        self,
        extracted_data: Dict,
        timeline: List[Dict],
        contradictions: List[Dict],
        patient_name: str,
        case_number: str
    ) -> str:
        """Generate a mock executive summary when LLM is unavailable - narrative style"""
        key_data = self._extract_key_data_for_executive(extracted_data, timeline, contradictions)
        
        # Create a more narrative, descriptive summary for medical reviewers
        bullets = [
            f"• Patient {patient_name} (Case: {case_number}) - {key_data['admission_discharge_info']}. Clinical review requested for health plan authorization.",
            f"• Patient presented with documented diagnoses: {key_data['primary_diagnoses']}. Initial clinical assessment and diagnostic workup completed.",
            f"• Treatment plan initiated with medications: {key_data['key_medications']}. Patient monitored for response to therapy.",
        ]
        
        if key_data['critical_labs'] != 'No critical abnormals':
            bullets.append(f"• Key diagnostic findings documented: {key_data['critical_labs']}. Results reviewed and incorporated into treatment decisions.")
        
        if key_data['key_events']:
            bullets.append(f"• Clinical course documented with significant events in medical record. Timeline shows progression of care and treatment response.")
        
        bullets.append(f"• Current clinical status: Patient managed per standard clinical protocols. Documentation includes care progression and outcomes.")
        
        if key_data['concerns'] != 'None identified':
            bullets.append(f"• Clinical considerations for review: {key_data['concerns']}. These items may require additional clarification or documentation.")
        else:
            bullets.append(f"• Clinical documentation appears complete with no identified gaps at initial review.")
        
        return '\n'.join(bullets)

    def _format_allergies_for_prompt(self, allergies: List) -> str:
        """Format allergies for prompt - handles both string and dict formats"""
        if not allergies:
            return 'Not explicitly documented'
        
        allergy_names = []
        for a in allergies:
            if isinstance(a, str):
                # Old format - string
                allergy_names.append(a)
            elif isinstance(a, dict):
                # New format - dictionary with 'allergen' field
                allergen = a.get('allergen', '')
                if allergen:
                    allergy_names.append(allergen)
        
        return ', '.join(allergy_names) if allergy_names else 'Not explicitly documented'

    def _format_timeline_for_prompt(self, timeline: List[Dict]) -> str:
        """Format timeline for prompt - Include ALL events"""
        lines = []
        for event in timeline:  # Include all timeline events
            date = event.get('date', 'Unknown date')
            desc = event.get('description', 'No description')
            event_type = event.get('event_type', '')
            lines.append(f"- {date}: [{event_type}] {desc}")
        return "\n".join(lines) if lines else "No timeline events available"

    def _format_contradictions_for_prompt(self, contradictions: List[Dict]) -> str:
        """Format potential missing info for prompt - Include ALL items"""
        if not contradictions:
            return "No potential missing information identified"

        lines = []
        for c in contradictions:  # Include all contradiction items
            desc = c.get('description', 'No description')
            suggestion = c.get('suggestion', '')
            if suggestion:
                lines.append(f"- {desc} ({suggestion})")
            else:
                lines.append(f"- {desc} (May require review)")
        return "\n".join(lines)

    def _generate_mock_summary(
        self,
        extracted_data: Dict,
        timeline: List[Dict],
        contradictions: List[Dict],
        patient_name: str,
        case_number: str
    ) -> str:
        """Generate a formatted mock summary"""
        # Format diagnoses
        diagnoses = extracted_data.get('diagnoses', [])
        diagnoses_text = []
        for dx in diagnoses:
            if isinstance(dx, str):
                diagnoses_text.append(dx)
            elif isinstance(dx, dict):
                diagnoses_text.append(dx.get('name', ''))
        diagnoses_list = ', '.join(diagnoses_text) if diagnoses_text else 'Not explicitly documented'
        
        allergies_list = self._format_allergies_for_prompt(extracted_data.get('allergies', []))

        medications_summary = ""
        for med in extracted_data.get('medications', [])[:5]:
            name = med.get('name', 'Unknown')
            dosage = med.get('dosage', '')
            freq = med.get('frequency', '')
            medications_summary += f"- {name} {dosage} {freq}\n"

        medications_summary = medications_summary or "Not explicitly documented\n"

        timeline_summary = ""
        for event in timeline[:8]:
            date = event.get('date', 'Unknown')
            desc = event.get('description', '')
            timeline_summary += f"- {date}: {desc}\n"

        contradictions_summary = ""
        if contradictions:
            for c in contradictions[:3]:
                desc = c.get('description', '')
                suggestion = c.get('suggestion', '')
                if suggestion:
                    contradictions_summary += f"- {desc} ({suggestion})\n"
                else:
                    contradictions_summary += f"- {desc} (May require review)\n"
        else:
            contradictions_summary = "No potential missing information identified.\n"

        labs = extracted_data.get('labs', [])
        abnormal_count = len([lab for lab in labs if lab.get('abnormal')])

        medications_summary = medications_summary if medications_summary.strip() else 'Not explicitly documented\n'

        summary = f"""
CLINICAL CASE SUMMARY

PATIENT: {patient_name}
CASE NUMBER: {case_number}
DATE PREPARED: {self._get_current_date()}

═══════════════════════════════════════════════════════════

1. PATIENT OVERVIEW

This summary presents clinical information extracted from medical records.

2. CHIEF COMPLAINT & PRESENTATION

Chief complaint information as documented in medical records.

3. CURRENT DIAGNOSES

{diagnoses_list}

4. MEDICATION SUMMARY

Current Medications:
{medications_summary}

Known Allergies: {allergies_list}

5. CLINICAL TIMELINE HIGHLIGHTS

{timeline_summary or 'No timeline events available'}

6. KEY LAB/DIAGNOSTIC FINDINGS

{len(labs)} laboratory results documented.
{abnormal_count} abnormal results identified.

7. PROCEDURES PERFORMED

{len(extracted_data.get('procedures', []))} procedures documented in the medical record.

8. POTENTIAL MISSING INFO / ITEMS THAT MAY REQUIRE REVIEW

{contradictions_summary}

═══════════════════════════════════════════════════════════

This summary is informational only and does not constitute a utilization 
management decision. All information is presented as documented in source records.
"""
        return summary.strip()

    def _get_current_date(self) -> str:
        """Get current date in MM/DD/YYYY format"""
        from datetime import datetime
        return datetime.now().strftime("%m/%d/%Y")


# Singleton instance
summary_service = SummaryService()
