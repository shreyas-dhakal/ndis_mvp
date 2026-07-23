# Import Libraries:
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Literal, Optional, TypedDict

from dotenv import load_dotenv
from pydantic import BaseModel
from psycopg_pool import ConnectionPool

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from src.ai.config import VOICE_PROVIDER
from src.ai.runtime import transcribe_audio_file
from .generate_pdf import soap_to_pdf
from .local_llm import invoke_structured
from src.project_guards import require_valid_input, require_valid_output

load_dotenv()

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated_pdfs"

conn_string = os.getenv("DATABASE_URL")
if not conn_string:
    print("Please add the db url key in .env")
else:
    print("DB url loaded successfullty")


class NDISProgressNote(BaseModel):
    subjective: str
    objective: str
    assessment: str
    plan: str
    linked_goals: list[str] = []
    support_type: str
    participant_voice: str
    risks_incidents: str
    consent_noted: Optional[bool] = None


class AgentState(TypedDict):
    audio_path: Optional[str]
    transcript: str
    transcript_lines: list
    goals_context: str
    progress_note: Optional[NDISProgressNote]
    human_feedback: Optional[str]
    pdf_path: Optional[str]
    final_response: str


sys_prompt = """
You are an experienced NDIS support documentation assistant.

Convert the conversation transcript into a professional NDIS Progress Note.
- Use ONLY information present in the transcript.
- Link activities to NDIS goals where relevant.
- Capture the participant's voice and preferences.
- Be factual, concise, and person-centred.
- For text fields, write "Not documented" if information is missing.
- For linked_goals, use an empty list [] if no goals are mentioned.
- For consent_noted, use true if consent was clearly given, false if clearly not given,
  and null if consent was not discussed.
"""

human_prompt = """
Transcript:
{transcript}

Participant's known goals (if available):
{goals_context}
"""

revision_prompt = """
Previous NDIS Progress Note:
{previous_note}

Apply this feedback and generate an improved version:
{feedback}
"""
def transcribe_audio(state: AgentState) -> dict:
    audio_path = state.get("audio_path")
    if not audio_path:
        return {}

    model_override = (
        state.get("whisper_model_size", "small")
        if VOICE_PROVIDER == "faster_whisper"
        else None
    )
    transcript_text, lines = transcribe_audio_file(audio_path, model=model_override)
    return {"transcript": transcript_text, "transcript_lines": lines}


def generate_progress_note(state: AgentState):
    transcript = state.get("transcript", "").strip()
    if not transcript:
        raise ValueError("Transcript is empty.")

    goals_context = state.get("goals_context", "No goals provided.")
    if not state.get("human_feedback"):
        result = invoke_structured(
            NDISProgressNote,
            system_prompt=sys_prompt,
            user_prompt=human_prompt.format(
                transcript=transcript,
                goals_context=goals_context,
            ),
        )
    else:
        prior = state.get("progress_note")
        result = invoke_structured(
            NDISProgressNote,
            system_prompt=sys_prompt,
            user_prompt=revision_prompt.format(
                previous_note=prior.model_dump_json() if prior else "{}",
                feedback=state["human_feedback"],
            ),
        )
    require_valid_output(result, session_date=date.today(), label="generated progress note")
    return {"progress_note": result}


def human_review_node(state: AgentState) -> AgentState:
    note = state.get("progress_note")
    if not note:
        return {}

    feedback = interrupt(
        {
            "note": note.model_dump(),
            "question": "Approve this NDIS Progress Note? Reply YES or provide correction.",
        }
    )
    feedback_text = feedback if isinstance(feedback, str) else str(feedback or "")
    normalized_feedback = feedback_text.strip()
    if normalized_feedback.lower() in ("ok", "yes", "approved", "y"):
        return {"human_feedback": None}
    require_valid_input(normalized_feedback, field_name="human feedback")
    return {"human_feedback": normalized_feedback}


def finalize_node(state: AgentState) -> AgentState:
    if state.get("human_feedback"):
        return {"final_response": "Pending further revision"}

    soap_data = state.get("progress_note")
    if not soap_data:
        return {"final_response": "Error: Note Missing"}

    pdf_path = OUTPUT_DIR / f"soap_{uuid.uuid4().hex}.pdf"
    soap_to_pdf(soap_data, pdf_path)
    return {
        "pdf_path": str(pdf_path),
        "final_response": "NDIS Progress Note approved and saved",
    }


def check_humanfb(state: AgentState) -> Literal["generate_progress_note", "finalize_node"]:
    if not state.get("human_feedback"):
        return "finalize_node"
    return "generate_progress_note"


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("transcribe_audio", transcribe_audio)
    graph.add_node("generate_progress_note", generate_progress_note)
    graph.add_node("human_review_node", human_review_node)
    graph.add_node("finalize_node", finalize_node)

    graph.add_edge(START, "transcribe_audio")
    graph.add_edge("transcribe_audio", "generate_progress_note")
    graph.add_edge("generate_progress_note", "human_review_node")
    graph.add_conditional_edges("human_review_node", check_humanfb)
    graph.add_edge("finalize_node", END)

    pool = ConnectionPool(
        conn_string,
        kwargs={"autocommit": True, "row_factory": None, "prepare_threshold": None},
    )
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()
    return graph.compile(checkpointer=checkpointer)


workflow = None


def get_workflow():
    global workflow
    if workflow is None:
        workflow = build_graph()
    return workflow
