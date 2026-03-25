"""Upload Agent Service - Conversational agent for managing the upload flow"""

import uuid
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum
from datetime import datetime
import re

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.pdf_analyzer_service import PatientInfo, AnalysisResult, pdf_analyzer_service
from app.models.upload_session import UploadSession as UploadSessionModel
from app.repositories.upload_session_repository import UploadSessionRepository
from app.services.upload_session_storage_cleanup import is_resumable_upload_state
from app.services.llm.llm_factory import get_tier1_llm_service
from app.services.llm_utils import extract_json_from_response
from app.services.prompts import upload_prompts

logger = logging.getLogger(__name__)


class ConversationState(str, Enum):
    """States in the upload conversation flow"""
    GREETING = "greeting"
    WAITING_FOR_FILES = "waiting_for_files"
    CONFIRM_ANALYSIS = "confirm_analysis"
    COLLECTING_DATA = "collecting_data" # consolidated state for LLM loop
    REVIEW_SUMMARY = "review_summary"
    PROCESSING = "processing"
    COMPLETE = "complete"
    ERROR = "error"


class MessageType(str, Enum):
    """Types of agent messages"""
    GREETING = "greeting"
    QUESTION = "question"
    CONFIRMATION = "confirmation"
    STATUS = "status"
    ERROR = "error"
    SUCCESS = "success"


@dataclass
class QuickAction:
    """Quick action button for user responses"""
    label: str
    value: str
    variant: str = "default"  # default, primary, secondary, destructive


@dataclass
class AgentMessage:
    """Message from the agent"""
    id: str
    message: str
    type: MessageType
    timestamp: str
    actions: List[QuickAction] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    current_field: Optional[str] = None  # Deprecated in LLM flow, kept for compatibility
    extracted_data: Optional[Dict] = None
    files_info: Optional[List[Dict]] = None
    progress: Optional[int] = None  # 0-100 for processing status
    
    def to_dict(self) -> Dict:
        result = asdict(self)
        result["type"] = self.type.value
        # Rename current_field to field for API compatibility
        result["field"] = result.pop("current_field")
        return result


@dataclass
class UserMessage:
    """Message from the user"""
    id: str
    message: str
    timestamp: str
    files: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return asdict(self)


def intake_quick_actions_for_message(
    collected_data: Dict[str, Any],
    missing_fields: List[str],
    message_text: str,
) -> List[QuickAction]:
    """
    Quick-reply buttons for structured intake (case #, request type, priority).

    Substring-only matching failed when the LLM said e.g. "type of request" instead of
    "request type", or mentioned "case number" in the same turn as a follow-up question.
    We primarily key off the next missing REQUIRED field, with message phrases as backup.
    """
    next_field = missing_fields[0] if missing_fields else None
    msg_l = (message_text or "").lower()

    if not collected_data.get("case_number") and (
        next_field == "case_number" or "case number" in msg_l
    ):
        random_case = f"UM-{uuid.uuid4().hex[:6].upper()}"
        return [
            QuickAction(f"Use {random_case}", random_case),
            QuickAction("I'll provide one", "I'll provide one"),
        ]
    if not collected_data.get("request_type") and (
        next_field == "request_type"
        or "request type" in msg_l
        or "type of request" in msg_l
        or "type of review" in msg_l
        or "kind of request" in msg_l
        or "inpatient or outpatient" in msg_l
    ):
        return [
            QuickAction("Inpatient", "Inpatient"),
            QuickAction("Outpatient", "Outpatient"),
            QuickAction("DME", "DME"),
            QuickAction("Pharmacy", "Pharmacy"),
        ]
    if not collected_data.get("priority") and (
        next_field == "priority" or "priority" in msg_l or "urgency" in msg_l
    ):
        return [
            QuickAction("Routine", "Routine"),
            QuickAction("Expedited", "Expedited"),
            QuickAction("Urgent", "Urgent", variant="destructive"),
        ]
    return []


class UploadAgentService:
    """Conversational agent for managing the upload flow - LLM Powered"""
    
    REQUIRED_FIELDS = [
        "patient_name", "dob", "mrn", "case_number", "priority",
        "request_type", "requested_service", "request_date"
    ]
    
    def __init__(self):
        self.repository = UploadSessionRepository()
    
    def _get_llm(self):
        return get_tier1_llm_service()
    
    def start_session(self, db: Session, user_id: Optional[str] = None) -> tuple[str, AgentMessage]:
        """Start a new upload session and return greeting"""
        session_id = str(uuid.uuid4())
        
        greeting = AgentMessage(
            id=str(uuid.uuid4()),
            message="Hey! I'm your UM Assistant. Drop your medical records here and I'll help you set up the case. You can upload multiple PDFs at once.",
            type=MessageType.GREETING,
            timestamp=datetime.utcnow().isoformat(),
            actions=[]
        )
        
        session = UploadSessionModel(
            id=session_id,
            user_id=user_id,
            state=ConversationState.WAITING_FOR_FILES.value,
            patient_info=PatientInfo().to_dict(),
            messages=[{"role": "agent", **greeting.to_dict()}]
        )
        
        self.repository.create(db, session)
        return session_id, greeting

    def get_session(self, db: Session, session_id: str) -> Optional[UploadSessionModel]:
        """Get session by ID"""
        return self.repository.get_by_id(db, session_id)

    def list_resumable_drafts(self, db: Session, user_id: str) -> List[UploadSessionModel]:
        """Sessions the user can continue (no case yet, resumable state, at least one uploaded file)."""
        rows = self.repository.get_by_user(db, user_id)
        return [
            s
            for s in rows
            if s.case_id is None
            and is_resumable_upload_state(s.state)
            and len(s.files or []) > 0
        ]

    async def handle_files_uploaded(
        self, 
        db: Session,
        session_id: str, 
        analysis_result: AnalysisResult
    ) -> AgentMessage:
        """Handle files being uploaded - initializes context and triggers Agent"""
        session = self.repository.get_by_id(db, session_id)
        if not session:
            return self._error_message("Session not found. Please start over.")
        
        # 1. Check for non-medical documents early (only if guardrail is enabled)
        invalid_files = []
        valid_files = []
        
        if settings.ENABLE_MEDICAL_GUARDRAIL:
            for f in analysis_result.files:
                # Check keyword-based detection (per-file, most reliable)
                is_medical = True
                category = f.detected_type
                
                # If keyword detection flagged it as non-medical
                if f.detected_type.startswith("non_medical_"):
                    is_medical = False
                    category = f.detected_type.replace("non_medical_", "").title()
                
                if not is_medical:
                    invalid_files.append((f, category))
                else:
                    valid_files.append(f)
        else:
            # Guardrail disabled - accept all files
            valid_files = analysis_result.files

        # 2. Handle rejection if any invalid files found
        if settings.ENABLE_MEDICAL_GUARDRAIL and invalid_files:
            # For now, if even ONE file is invalid, we report it and stay in WAITING_FOR_FILES
            # In a more advanced version, we could keep the valid ones.
            # But the requirement is to block non-medical docs.
            
            rejection_details = []
            for f, category in invalid_files:
                rejection_details.append(f"'{f.file_name}' (detected as {category})")
            
            message = f"I detected that the following file(s) are not medical records: {', '.join(rejection_details)}. " \
                      f"I can only process clinical documentation for Utilization Management reviews. " \
                      f"I've removed these files for you. Please upload valid medical records (e.g., Discharge Summary, Lab Report)."
            
            # Record rejection in messages
            agent_msg = AgentMessage(
                id=str(uuid.uuid4()),
                message=message,
                type=MessageType.ERROR,
                timestamp=datetime.utcnow().isoformat(),
                actions=[QuickAction(label="Got it", value="clear_error", variant="primary")]
            )
            
            msgs = list(session.messages or [])
            msgs.append({"role": "agent", **agent_msg.to_dict()})
            session.messages = msgs
            # Keep state as WAITING_FOR_FILES
            session.updated_at = datetime.utcnow()
            db.commit()
            
            return agent_msg

        # 3. Update session with valid file info
        session.files = [
            {
                "name": f.file_name,
                "path": f.file_path,
                "pages": f.page_count,
                "size": f.file_size,
                "type": f.detected_type
            }
            for f in valid_files
        ]

        # Mirror the UI "Uploading …" line so refresh/resume shows the user's upload turn.
        names = [f.get("name") or "file" for f in (session.files or [])]
        n = len(names)
        upload_caption = (
            f"Uploading {n} file{'s' if n != 1 else ''}: {', '.join(names)}"
            if names
            else "Uploading files"
        )
        user_upload_row = UserMessage(
            id=str(uuid.uuid4()),
            message=upload_caption,
            timestamp=datetime.utcnow().isoformat(),
            files=names,
        )
        msgs_upload = list(session.messages or [])
        msgs_upload.append({"role": "user", **user_upload_row.to_dict()})
        session.messages = msgs_upload

        # 2. Merge initial extraction result into session
        if analysis_result.patient_info:
            p_info = dict(session.patient_info) if session.patient_info else {}
            
            # Helper to set if empty
            def set_if_empty(key, source_val):
                if not p_info.get(key) or p_info.get(key) in ["None", "null", "N/A"]:
                    if source_val:
                        p_info[key] = source_val

            set_if_empty("name", analysis_result.patient_info.name)
            set_if_empty("dob", analysis_result.patient_info.dob)
            set_if_empty("mrn", analysis_result.patient_info.mrn)
            set_if_empty("gender", analysis_result.patient_info.gender)
            set_if_empty("encounter_date", analysis_result.patient_info.encounter_date)
            set_if_empty("provider", analysis_result.patient_info.provider)
            set_if_empty("facility", analysis_result.patient_info.facility)
            set_if_empty("diagnosis", analysis_result.patient_info.diagnosis)
            
            session.patient_info = p_info
            
            # 2.5 Map session level fields from analysis
            if analysis_result.patient_info.request_type:
                session.request_type = analysis_result.patient_info.request_type
            
            # Default requested_service to "UM Review" if not found
            if not session.requested_service:
                session.requested_service = "UM Review"
            
        # 3. Transition to CONFIRM_ANALYSIS state
        session.state = ConversationState.CONFIRM_ANALYSIS.value
        session.updated_at = datetime.utcnow()
        db.commit()
        
        # 4. Return summary message with actions
        return self._show_analysis_summary(db, session, analysis_result)

    async def process_message(
        self,
        db: Session,
        session_id: str,
        user_message: str,
    ) -> AgentMessage:
        """
        Process a user message. By default runs the LangGraph orchestrator (`upload_agent_graph`).
        Set `settings.USE_UPLOAD_LANGGRAPH=False` to use the legacy linear implementation.
        """
        if settings.USE_UPLOAD_LANGGRAPH:
            from app.services.upload_agent_graph import invoke_upload_message

            return await invoke_upload_message(db, session_id, user_message)
        return await self._process_message_legacy(db, session_id, user_message)

    async def _process_message_legacy(
        self,
        db: Session,
        session_id: str,
        user_message: str,
    ) -> AgentMessage:
        """Pre-LangGraph orchestration (rollback / scripts)."""
        session = self.repository.get_by_id(db, session_id)
        if not session:
            return self._error_message("Session not found. Please start over.")

        user_msg = UserMessage(
            id=str(uuid.uuid4()),
            message=user_message,
            timestamp=datetime.utcnow().isoformat(),
        )

        messages = list(session.messages or [])
        messages.append({"role": "user", **user_msg.to_dict()})
        session.messages = messages
        session.updated_at = datetime.utcnow()
        db.commit()

        if session.state == ConversationState.WAITING_FOR_FILES.value:
            agent_msg = AgentMessage(
                id=str(uuid.uuid4()),
                message="I'm waiting for you to upload some files first. Please upload your PDFs.",
                type=MessageType.QUESTION,
                timestamp=datetime.utcnow().isoformat(),
            )
            msgs = list(session.messages or [])
            msgs.append({"role": "agent", **agent_msg.to_dict()})
            session.messages = msgs
            session.updated_at = datetime.utcnow()
            db.commit()
            return agent_msg

        if session.state == ConversationState.CONFIRM_ANALYSIS.value:
            msg_lower = user_message.lower().strip()
            if msg_lower in ["yes", "yes, looks good", "looks good", "correct", "confirm"]:
                session.state = ConversationState.COLLECTING_DATA.value
                db.commit()
            else:
                session.state = ConversationState.COLLECTING_DATA.value
                db.commit()

        if session.state == ConversationState.REVIEW_SUMMARY.value:
            msg_lower = user_message.lower().strip()
            if msg_lower in ["yes", "start", "process", "start processing", "confirm", "go", "looks good"]:
                return self._start_processing_message(db, session)
            session.state = ConversationState.COLLECTING_DATA.value
            db.commit()

        return await self._generate_and_save_agent_response(db, session)

    async def _generate_and_save_agent_response(
        self, 
        db: Session, 
        session: UploadSessionModel,
        is_initial_analysis: bool = False
    ) -> AgentMessage:
        """Core logic: Build context, call LLM, update state, save response"""
        
        # A. Prepare Context
        collected_data = self._get_collected_data(session)
        missing_fields = [f for f in self.REQUIRED_FIELDS if not collected_data.get(f)]
        
        # File info summary
        file_count = len(session.files or [])
        total_pages = sum(f.get("pages", 0) for f in (session.files or []))
        file_info = f"{file_count} PDF files uploaded ({total_pages} total pages)."
        if is_initial_analysis:
            file_info += " Just finished analyzing documents."

        # B. Build Prompt
        system_prompt = upload_prompts.build_upload_agent_system_prompt(
            collected_data=collected_data,
            missing_fields=missing_fields,
            file_info=file_info,
            previous_messages=session.messages[-10:] # Last 10 messages for context
        )

        # C. Call LLM
        llm_service = self._get_llm()
        if not llm_service.is_available():
            # Fallback if no LLM
            return self._error_message("AI Service unavailable. Please try again.")

        try:
             # Depending on user implementation, we might send chat history + system prompt
             # For now, we'll send the strict system prompt and the LAST user message only 
             # (or rely on the system prompt containing the history if we formatted it there, 
             # but the prompt builder I wrote expects us to pass history or handles it implicitly? 
             # Let's check `build_upload_agent_system_prompt` signature. 
             # Ah, it doesn't embed history in the prompt text, it takes `previous_messages` but the implementation I wrote 
             # just passes it in. I should probably just let the LLM see the messages naturally.)
             
             # Actually, simpler: System Prompt sets the stage. We pass recent messages as 'messages'.
             
            messages_payload = [{"role": "system", "content": system_prompt}]
            
            # Add recent history (excluding the very first system greeting perhaps)
            # We need to map our internal message format to OpenAI format
            # Our messages are stored as dicts with "role" (agent/user) and content keys
            for m in (session.messages or [])[-6:]: # Last 6 messages
                role = "assistant" if m["role"] == "agent" else "user"
                content = m.get("message", "")
                messages_payload.append({"role": role, "content": content})

            response, _ = await llm_service.chat_completion(
                messages=messages_payload,
                temperature=0.2, # Low temp for data extraction
                response_format={"type": "json_object"}
            )
            
            # D. Parse Response
            result = extract_json_from_response(response)
            
            # E. Update Session with Extracted Data
            updates = result.get("extracted_updates", {})
            if updates:
                self._apply_updates(session, updates)
                # Re-calculate missing fields after updates to check if we are done
                collected_data = self._get_collected_data(session)
                missing_fields = [f for f in self.REQUIRED_FIELDS if not collected_data.get(f)]
            
            # F. Determine Next Step
            # Check if LLM signals completion or if we are techincally done
            llm_signals_done = result.get("next_step") == "ready_for_review"
            
            # Define critical fields that CANNOT be defaulted
            critical_fields = ["patient_name", "dob", "mrn"]
            has_critical_missing = any(f in missing_fields for f in critical_fields)
            
            if not missing_fields or (llm_signals_done and not has_critical_missing):
                # If LLM thinks we're done (and we have criticals), or we simply HAVE everything:
                # Auto-fill any remaining checks to ensure clean state
                
                updates_made = False
                
                if not collected_data.get("case_number"):
                    session.case_number = f"UM-{uuid.uuid4().hex[:6].upper()}"
                    updates_made = True
                
                if not collected_data.get("priority"):
                    session.priority = "Routine"
                    updates_made = True
                    
                if not collected_data.get("request_type"):
                    session.request_type = "Inpatient" # Default compliant type
                    updates_made = True
                
                if not collected_data.get("requested_service"):
                    session.requested_service = "UM Review"
                    updates_made = True
                    
                if not collected_data.get("request_date"):
                    session.request_date = datetime.now().strftime("%m/%d/%Y")
                    updates_made = True
                
                if updates_made:
                    db.commit()
                    # Re-verify missing fields
                    collected_data = self._get_collected_data(session)
                    missing_fields = [f for f in self.REQUIRED_FIELDS if not collected_data.get(f)]
                
                if not missing_fields:
                    return self._show_summary_and_confirm(db, session, result.get("message"))
            
            # DEAD END FIX: If LLM thinks it's done but we are missing CRITICAL fields, override the message
            if llm_signals_done and has_critical_missing:
                missing_crit = [f for f in missing_fields if f in critical_fields][0]
                readable = missing_crit.replace("_", " ").title()
                if missing_crit == "dob": readable = "Date of Birth"
                if missing_crit == "mrn": readable = "MRN"
                
                # Force the message to be a question about the missing field
                result["message"] = f"I'm almost ready, but I need the **{readable}** before I can finalize the setup. Could you please provide it?"

            # G. Construct Agent Message
            message_text = result.get("message", "I didn't quite catch that.")

            # Next field we're collecting (drives UI e.g. date picker); omit on summary/confirmation flows
            next_field = missing_fields[0] if missing_fields else None
            actions = intake_quick_actions_for_message(
                collected_data, missing_fields, message_text
            )

            agent_msg = AgentMessage(
                id=str(uuid.uuid4()),
                message=message_text,
                type=MessageType.QUESTION,
                timestamp=datetime.utcnow().isoformat(),
                actions=actions,
                extracted_data=updates,
                current_field=next_field,
            )
            
            # Save
            msgs = list(session.messages or [])
            msgs.append({"role": "agent", **agent_msg.to_dict()})
            session.messages = msgs
            session.updated_at = datetime.utcnow()
            db.commit()
            
            return agent_msg

        except Exception as e:
            logger.error(f"Error in Agent generation: {e}", exc_info=True)
            return self._error_message("I'm having trouble processing that. Could you repeat?")

    def _get_collected_data(self, session: UploadSessionModel) -> Dict:
        """Helper to flatten session data into a single dict"""
        p_info = session.patient_info if isinstance(session.patient_info, dict) else {}
        
        return {
            "patient_name": p_info.get("name"),
            "dob": p_info.get("dob"),
            "mrn": p_info.get("mrn"),
            "case_number": session.case_number,
            "priority": session.priority,
            "request_type": session.request_type,
            "requested_service": session.requested_service,
            "request_date": session.request_date,
            "diagnosis": p_info.get("diagnosis"), # Include diagnosis
            "files": session.files # Added to return files
        }

    def _apply_updates(self, session: UploadSessionModel, updates: Dict):
        """Apply extracted updates to session model"""
        p_info = dict(session.patient_info) if session.patient_info else {}
        
        # Patient Info updates
        if "patient_name" in updates: p_info["name"] = updates["patient_name"]
        if "dob" in updates: p_info["dob"] = updates["dob"]
        if "mrn" in updates: p_info["mrn"] = updates["mrn"]
        
        session.patient_info = p_info
        
        # Session fields
        if "case_number" in updates: session.case_number = updates["case_number"]
        if "priority" in updates and updates["priority"]: session.priority = updates["priority"].title()
        if "urgency" in updates and updates["urgency"]: session.priority = updates["urgency"].title() # Map urgency to priority
        if "request_type" in updates: session.request_type = updates["request_type"]
        if "requested_service" in updates: session.requested_service = updates["requested_service"]
        if "request_date" in updates: session.request_date = updates["request_date"]

    def _show_summary_and_confirm(self, db: Session, session: UploadSessionModel, intro_message: Optional[str] = None) -> AgentMessage:
        """Show summary when all data is collected"""
        session.state = ConversationState.REVIEW_SUMMARY.value
        db.commit()
        
        data = self._get_collected_data(session)
        summary_lines = [
            f"**Patient:** {data.get('patient_name')}",
            f"**DOB:** {data.get('dob')}",
            f"**MRN:** {data.get('mrn')}",
            f"**Case:** {data.get('case_number')}",
            f"**Priority:** {data.get('priority')}" if data.get('priority') else "**Priority:** Not Set",
            f"**Request Type:** {data.get('request_type')}",
            f"**Diagnosis:** {data.get('diagnosis')}", # Added Diagnosis to summary
            f"**Service:** {data.get('requested_service')}",
            f"**Date:** {data.get('request_date')}",
        ]
        
        summary_text = "\\n".join(summary_lines)
        
        intro = intro_message if intro_message else "I have everything I need! Here is the summary:"
        
        msg = AgentMessage(
            id=str(uuid.uuid4()),
            message=f"{intro}\\n\\n{summary_text}\\n\\nReady to process?",
            type=MessageType.CONFIRMATION,
            timestamp=datetime.utcnow().isoformat(),
            actions=[
                QuickAction(label="Start Processing", value="start", variant="primary"),
                QuickAction(label="Edit Details", value="edit", variant="secondary")
            ],
            current_field=None,
        )
        
        msgs = list(session.messages or [])
        msgs.append({"role": "agent", **msg.to_dict()})
        session.messages = msgs
        db.commit()
        
        return msg

    def _start_processing_message(self, db: Session, session: UploadSessionModel) -> AgentMessage:
        """Return message indicating ready to start processing"""
        session.processing_status = "ready_to_start"
        session.state = ConversationState.PROCESSING.value
        db.commit()

        agent_msg = AgentMessage(
            id=str(uuid.uuid4()),
            message="Starting now! I'll extract clinical data, build the timeline, and generate your UM summary. This usually takes about a minute...",
            type=MessageType.STATUS,
            timestamp=datetime.utcnow().isoformat(),
            progress=0,
        )
        msgs = list(session.messages or [])
        msgs.append({"role": "agent", **agent_msg.to_dict()})
        session.messages = msgs
        session.updated_at = datetime.utcnow()
        db.commit()
        return agent_msg
    
    def update_processing_status(
        self, 
        db: Session,
        session_id: str, 
        status: str, 
        progress: int,
        case_id: Optional[str] = None
    ) -> Optional[AgentMessage]:
        """Update processing status and return status message"""
        session = self.repository.get_by_id(db, session_id)
        if not session:
            return None
        
        session.processing_status = status
        session.processing_progress = progress
        session.updated_at = datetime.utcnow()
        
        if case_id:
            session.case_id = case_id
        
        # Status messages for different stages
        status_messages = {
            "uploading": "Uploading files...",
            "extracting_text": "Extracting text from PDFs...",
            "chunking": "Building document chunks...",
            "embedding": "Creating embeddings...",
            "clinical_extraction": "Extracting clinical information...",
            "timeline": "Building timeline...",
            "red_flags": "Detecting red flags...",
            "contradictions": "Checking for contradictions...",
            "summary": "Generating summary...",
            "complete": "Done! Your case is ready for review.",
            "error": "Something went wrong during processing."
        }
        
        message_text = status_messages.get(status, f"Processing: {status}")
        
        if status == "complete":
            session.state = ConversationState.COMPLETE.value
            db.commit()
            return AgentMessage(
                id=str(uuid.uuid4()),
                message=message_text,
                type=MessageType.SUCCESS,
                timestamp=datetime.utcnow().isoformat(),
                progress=100,
                actions=[
                    QuickAction(label="View Case", value=f"view_case:{session.case_id}", variant="primary"),
                    QuickAction(label="Upload Another", value="new_upload", variant="secondary")
                ]
            )
        elif status == "error":
            session.state = ConversationState.ERROR.value
            db.commit()
            return AgentMessage(
                id=str(uuid.uuid4()),
                message=message_text,
                type=MessageType.ERROR,
                timestamp=datetime.utcnow().isoformat(),
                progress=progress,
                actions=[
                    QuickAction(label="Try Again", value="retry", variant="primary")
                ]
            )
        else:
            db.commit()
            return AgentMessage(
                id=str(uuid.uuid4()),
                message=message_text,
                type=MessageType.STATUS,
                timestamp=datetime.utcnow().isoformat(),
                progress=progress
            )
            
    def _error_message(self, message: str) -> AgentMessage:
        """Create an error message"""
        return AgentMessage(
            id=str(uuid.uuid4()),
            message=message,
            type=MessageType.ERROR,
            timestamp=datetime.utcnow().isoformat(),
            actions=[
                QuickAction(label="Start Over", value="restart", variant="primary")
            ]
        )
    
    def delete_session(self, db: Session, session_id: str) -> bool:
        """Delete a session"""
        return self.repository.delete(db, session_id)
    
    def get_session_data_for_case(self, db: Session, session_id: str) -> Optional[Dict]:
        """Get session data formatted for case creation"""
        session = self.repository.get_by_id(db, session_id)
        if not session:
            return None
        return self._get_collected_data(session)


    def _show_analysis_summary(self, db: Session, session: UploadSessionModel, analysis: AnalysisResult) -> AgentMessage:
        """Show summary of analyzed files and extracted info"""
        
        # Build formatted summary
        file_count = len(analysis.files)
        total_pages = analysis.total_pages
        
        p = analysis.patient_info
        summary = f"I extracted the following information from the documents:\\n\\n"
        
        fields = []
        if p.name: fields.append(f"**Patient:** {p.name}")
        if p.dob: fields.append(f"**DOB:** {p.dob}")
        if p.mrn: fields.append(f"**MRN:** {p.mrn}")
        if p.request_type: fields.append(f"**Request Type:** {p.request_type}")
        if p.diagnosis: fields.append(f"**Diagnosis:** {p.diagnosis}")
        
        if fields:
            summary += "\\n".join(fields)
        else:
            summary += "I couldn't find much specific patient info."
            
        summary += "\\n\\nDoes this look correct?"

        msg = AgentMessage(
            id=str(uuid.uuid4()),
            message=summary,
            type=MessageType.CONFIRMATION,
            timestamp=datetime.utcnow().isoformat(),
            actions=[
                QuickAction(label="Yes, looks good", value="Yes, looks good", variant="primary"),
                QuickAction(label="No, let me edit", value="No, let me edit", variant="secondary")
            ]
        )
        
        msgs = list(session.messages or [])
        msgs.append({"role": "agent", **msg.to_dict()})
        session.messages = msgs
        db.commit()
        
        return msg


# Singleton instance
upload_agent_service = UploadAgentService()
