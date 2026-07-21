import uuid
import os
import shutil
import json

from typing import Any, Optional
from langgraph.types import Command
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from src.agent import get_workflow
from src.agent import run_agent2
from src.project_guards import GuardValidationError
from src.rag import (
    answer_question,
    chat_completion,
    close_pool,
    delete_document,
    ensure_schema,
    get_connection,
    get_pool,
    ingest_upload,
    list_documents,
    OLLAMA_CHAT_MODEL,
    retrieve_chunks,
    store_generated_note,
)

UPLOAD_DIR = Path(__file__).resolve().parent / "uploaded_audio"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated_pdfs"

spine_pool = get_pool()

app = FastAPI(title="Agents MVP API")


def load_model_registry() -> dict[str, str]:
    raw = os.getenv("INFERENCE_MODEL_REGISTRY_JSON")
    if not raw:
        return {OLLAMA_CHAT_MODEL: OLLAMA_CHAT_MODEL}

    parsed = json.loads(raw)
    registry: dict[str, str] = {}
    for public_name, cfg in parsed.items():
        provider = (cfg or {}).get("provider")
        model_id = (cfg or {}).get("model_id")
        if provider != "ollama" or not model_id:
            continue
        registry[str(public_name)] = str(model_id)
    return registry or {OLLAMA_CHAT_MODEL: OLLAMA_CHAT_MODEL}


def resolve_inference_model(model: str) -> str:
    registry = load_model_registry()
    if model in registry:
        return registry[model]
    if model == OLLAMA_CHAT_MODEL:
        return OLLAMA_CHAT_MODEL
    return next(iter(registry.values()))


def openai_chat_response(*, model: str, content: str) -> dict[str, Any]:
    import time

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }

class TranscriptRequest(BaseModel):
    transcript:str

class ResumeRequest(BaseModel):
    thread_id: str
    feedback: str 

class TaskActionRequest(BaseModel):
    reviewer: str = "unknown"
    reason: Optional[str] = None


class ChatRequest(BaseModel):
    question: str


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = 4
    source_filter: Optional[str] = None
    record_type: Optional[str] = None
    entity_name: Optional[str] = None
    alpha: float = 0.55


class AgentRequest(RetrieveRequest):
    context_mode: str = "full"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionsRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float | None = None
    stream: bool = False


@app.on_event("startup")
def on_startup() -> None:
    ensure_schema()


@app.on_event("shutdown")
def on_shutdown() -> None:
    close_pool()

def extract_interrupt(result: dict):
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    return interrupts[0].value if hasattr(interrupts[0], "value") else interrupts[0]

async def build_done_response(result: dict, thread_id: str) -> dict:
    note_obj = result.get("progress_note")
    a2_task_created = False
    a2_trigger_id = None

    if note_obj:
        note_dict = note_obj.model_dump()
        record_id, record_timestamp = await store_generated_note(note_dict, thread_id)
        try:
            a2_result = run_agent2(record_id, record_timestamp, note_dict, spine_pool)
            a2_task_created = bool(a2_result.get("workflow_id"))
            a2_trigger_id = a2_result["decision"].get("trigger_id")
        except Exception as e:
            print(f"Agent2 classification failed: {e}")

    return {
        "thread_id": thread_id,
        "status": "done",
        "final_response": result.get("final_response"),
        "pdf_path": result.get("pdf_path"),
        "note": note_obj.model_dump() if note_obj else None,
        "a2_task_created": a2_task_created,
        "a2_trigger_id": a2_trigger_id,
    }

@app.get("/")
def home():
    return {"message": "Agents MVP API"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/stats")
def debug_stats():
    with get_connection() as conn:
        row = conn.execute(
            """
            select
              (select count(*) from entities) as entities_count,
              (select count(*) from documents) as documents_count,
              (select count(*) from records) as records_count,
              (select count(*) from chunks) as chunks_count
            """
        ).fetchone() or (0, 0, 0, 0)
    return {
        "entities_count": int(row[0] or 0),
        "documents_count": int(row[1] or 0),
        "records_count": int(row[2] or 0),
        "chunks_count": int(row[3] or 0),
    }


@app.get("/v1/models")
def list_models() -> dict[str, Any]:
    registry = load_model_registry()
    return {
        "object": "list",
        "data": [{"id": model_name} for model_name in registry],
    }


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionsRequest) -> dict[str, Any]:
    if req.stream:
        return openai_chat_response(model=req.model, content="Streaming not implemented")

    model_id = resolve_inference_model(req.model)
    content = chat_completion(
        [m.model_dump() for m in req.messages],
        model=model_id,
        temperature=req.temperature,
    )
    return openai_chat_response(model=req.model, content=content)


@app.get("/documents")
def get_documents():
    return list_documents()


@app.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    source: str = Form("local"),
    author: str = Form("user"),
    doc_type: str = Form("document"),
    entity_name: str | None = Form(None),
    entity_type: str = Form("person"),
    entity_aliases: str | None = Form(None),
):
    return await ingest_upload(
        file=file,
        source=source,
        author=author,
        doc_type=doc_type,
        entity_name=entity_name,
        entity_type=entity_type,
        entity_aliases=entity_aliases,
    )


@app.delete("/documents/{document_id}")
def remove_document(document_id: str):
    return delete_document(document_id)


@app.post("/ingest/file")
async def ingest_file(
    file: UploadFile = File(...),
    source: str = Form("local"),
    author: str = Form("user"),
    doc_type: str = Form("document"),
    entity_name: str | None = Form(None),
    entity_type: str = Form("person"),
    entity_aliases: str | None = Form(None),
):
    return await ingest_upload(
        file=file,
        source=source,
        author=author,
        doc_type=doc_type,
        entity_name=entity_name,
        entity_type=entity_type,
        entity_aliases=entity_aliases,
    )


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    return retrieve_chunks(
        query=req.query,
        top_k=req.top_k,
        source_filter=req.source_filter,
        record_type=req.record_type,
        entity_name=req.entity_name,
        alpha=req.alpha,
    )


@app.post("/agent/answer")
def agent_answer(req: AgentRequest):
    return answer_question(
        query=req.query,
        top_k=req.top_k,
        source_filter=req.source_filter,
        record_type=req.record_type,
        entity_name=req.entity_name,
        alpha=req.alpha,
        context_mode=req.context_mode,
    )


@app.post("/chat")
def chat(req: ChatRequest):
    return answer_question(query=req.question)

@app.post("/generate/audio")
async def generate_from_audio(
    file: UploadFile = File(...),
    whisper_model_size: str = Form("small")
):
    if not file:
        raise HTTPException(status_code=400, detail="Audio file is required")

    audio_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    
    with open(audio_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    workflow = get_workflow()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = workflow.invoke({
            "audio_path": str(audio_path),
            "whisper_model_size": whisper_model_size,
            "goals_context": "No goals provided."
        }, config=config)
    except GuardValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    interrupt_data = extract_interrupt(result)
    if interrupt_data:
        return {
            "thread_id": thread_id,
            "status": "awaiting_review",
            "note": interrupt_data.get("note"),
            "question": interrupt_data.get("question")
        }

    return await build_done_response(result, thread_id)

@app.post("/generate/text")
async def generate_from_text(request: TranscriptRequest):
    if not request.transcript or not request.transcript.strip():
        raise HTTPException(status_code=400, detail="Transcript cannot be empty")

    workflow = get_workflow()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        result = workflow.invoke({
            "transcript": request.transcript,
            "goals_context": "No goals provided."
        }, config=config)
    except GuardValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    interrupt_data = extract_interrupt(result)
    if interrupt_data:
        return {
            "thread_id": thread_id,
            "status": "awaiting_review",
            "note": interrupt_data.get("note"),
            "question": interrupt_data.get("question")
        }

    return await build_done_response(result, thread_id)

@app.post("/generate/resume")
async def resume_review(payload: ResumeRequest):
    workflow = get_workflow()
    config = {"configurable": {"thread_id": payload.thread_id}}

    try:
        result = workflow.invoke(Command(resume=payload.feedback), config=config)
    except GuardValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    interrupt_data = extract_interrupt(result)
    if interrupt_data:
        return {
            "thread_id": payload.thread_id,
            "status": "awaiting_review",
            "note": interrupt_data.get("note"),
            "question": interrupt_data.get("question")
        }

    return await build_done_response(result, payload.thread_id)

@app.get("/download/pdf")
def download_pdf(path: str):
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(
        path, 
        media_type="application/pdf", 
        filename=os.path.basename(path)
    )

@app.get("/tasks")
def list_tasks(view: str = "pending"):
    status_filter = "r.status = 'draft'" if view == "pending" else \
                    "r.status = 'confirmed' AND r.actioned_at IS NULL"

    with spine_pool.connection() as conn:
        rows = conn.execute(f"""
            SELECT r.id, r.body, r.created_at, l.to_record_id
            FROM records r
            JOIN links l ON l.from_record_id = r.id AND l.link_type = 'triggered_by'
            WHERE r.record_type = 'incident' AND {status_filter}
            ORDER BY (r.body->>'deadline')::timestamptz ASC
        """).fetchall()

    tasks = []
    for row in rows:
        body = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        tasks.append({
            "id": str(row[0]),
            "trigger_id": body["trigger_id"],
            "reasoning": body["reasoning"],
            "deadline": body["deadline"],
            "created_at": row[2].isoformat(),
            "source_record_id": str(row[3]),
        })
    return {"tasks": tasks}

@app.post("/tasks/{task_id}/approve")
def approve_task(task_id: str, payload: TaskActionRequest):
    with spine_pool.connection() as conn:
        result = conn.execute(
            "UPDATE records SET status='confirmed', confirmed_at=now(), confirmed_by=%(r)s WHERE id=%(id)s",
            {"r": payload.reviewer, "id": task_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            "INSERT INTO events (actor, action, record_id, params) VALUES (%(r)s, 'human.approve_task', %(id)s, '{}')",
            {"r": payload.reviewer, "id": task_id},
        )
    return {"status": "approved"}


@app.post("/tasks/{task_id}/dismiss")
def dismiss_task(task_id: str, payload: TaskActionRequest):
    with spine_pool.connection() as conn:
        result = conn.execute(
            "UPDATE records SET status='dismissed', confirmed_at=now(), confirmed_by=%(r)s WHERE id=%(id)s",
            {"r": payload.reviewer, "id": task_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found")
        conn.execute(
            "INSERT INTO events (actor, action, record_id, params) VALUES (%(r)s, 'human.dismiss_task', %(id)s, %(params)s)",
            {"r": payload.reviewer, "id": task_id, "params": json.dumps({"reason": payload.reason})},
        )
    return {"status": "dismissed"}

@app.post("/tasks/{task_id}/action")
def action_task(task_id: str, payload: TaskActionRequest):
    with spine_pool.connection() as conn:
        result = conn.execute(
            """
            UPDATE records
            SET actioned_at = now(), actioned_by = %(r)s
            WHERE id = %(id)s AND status = 'confirmed'
            """,
            {"r": payload.reviewer, "id": task_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Task not found, or not yet confirmed")
        conn.execute(
            "INSERT INTO events (actor, action, record_id, params) VALUES (%(r)s, 'human.action_task', %(id)s, '{}')",
            {"r": payload.reviewer, "id": task_id},
        )
    return {"status": "actioned"}
