import uuid
import os
import shutil
import json

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from langgraph.types import Command
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pathlib import Path
from pydantic import BaseModel
from src.agent import get_workflow
from src.agent import run_agent2
from src.ai.config import DEFAULT_CHAT_MODEL, DEFAULT_CHAT_TARGET, ModelTarget, normalize_provider
from src.project_guards import GuardValidationError
from fastapi.middleware.cors import CORSMiddleware
from src.rag import (
    answer_question,
    chat_completion,
    close_pool,
    delete_document,
    ensure_schema,
    get_connection,
    get_pool,
    ingest_upload,
    find_entity_candidates,
    list_documents,
    retrieve_chunks,
    store_generated_note,
)

UPLOAD_DIR = Path(__file__).resolve().parent / "uploaded_audio"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "generated_pdfs"

spine_pool = get_pool()



app = FastAPI(title="Agents MVP API")


allowed_origins = os.getenv("CORS_ALLOWED_ORIGINS","http://localhost:5173").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
def _default_model_registry() -> dict[str, ModelTarget]:
    return {DEFAULT_CHAT_MODEL: DEFAULT_CHAT_TARGET}


def load_model_registry() -> dict[str, ModelTarget]:
    raw = os.getenv("INFERENCE_MODEL_REGISTRY_JSON")
    if not raw:
        return _default_model_registry()

    parsed = json.loads(raw)
    registry: dict[str, ModelTarget] = {}
    for public_name, cfg in parsed.items():
        if not isinstance(cfg, dict):
            continue
        model_name = str(cfg.get("model") or cfg.get("model_id") or public_name).strip()
        if not model_name:
            continue
        registry[str(public_name)] = ModelTarget(
            provider=normalize_provider(cfg.get("provider"), default=DEFAULT_CHAT_TARGET.provider),
            model=model_name,
            deployment=str(
                cfg.get("deployment")
                or cfg.get("deployment_id")
                or cfg.get("model_id")
                or model_name
            ).strip(),
        )
    return registry or _default_model_registry()


def resolve_inference_model(model: str) -> ModelTarget:
    registry = load_model_registry()
    selected = registry.get(model)
    if selected is None and model == DEFAULT_CHAT_MODEL:
        selected = registry.get(DEFAULT_CHAT_MODEL)
    if selected is None:
        selected = next(iter(registry.values()))
    return selected


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
    feedback: str = ""
    entity_confirmed: Optional[bool] = None
    entity_name: Optional[str] = None
    entity_id: Optional[str] = None
    create_new_entity: bool = False

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
        record_id, record_timestamp = await store_generated_note(
            note_dict,
            thread_id,
            entity_name=result.get("confirmed_entity_name"),
            entity_id=result.get("confirmed_entity_id"),
            create_new_entity=result.get("create_new_entity", False),
        )
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
        "entity_id": result.get("confirmed_entity_id"),
        "a2_task_created": a2_task_created,
        "a2_trigger_id": a2_trigger_id,
    }


def build_review_response(result: dict, interrupt_data: dict, thread_id: str) -> dict:
    return {
        "thread_id": thread_id,
        "status": "awaiting_review",
        "note": interrupt_data.get("note"),
        "question": interrupt_data.get("question"),
        "review_type": interrupt_data.get("type", "note_review"),
        "entity_confirmation": interrupt_data if interrupt_data.get("type") == "entity_confirmation" else None,
        "transcript": result.get("transcript"),
        "transcript_lines": result.get("transcript_lines", []),
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

    target = resolve_inference_model(req.model)
    content = chat_completion(
        [m.model_dump() for m in req.messages],
        model=target.model,
        provider=target.provider,
        deployment=target.deployment,
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
    confirmation_token: str | None = Form(None),
    entity_confirmed: bool = Form(False),
    entity_id: str | None = Form(None),
    create_new_entity: bool = Form(False),
):
    return await ingest_upload(
        file=file,
        source=source,
        author=author,
        doc_type=doc_type,
        entity_name=entity_name,
        entity_type=entity_type,
        entity_aliases=entity_aliases,
        confirmation_token=confirmation_token,
        entity_confirmed=entity_confirmed,
        entity_id=entity_id,
        create_new_entity=create_new_entity,
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
    confirmation_token: str | None = Form(None),
    entity_confirmed: bool = Form(False),
    entity_id: str | None = Form(None),
    create_new_entity: bool = Form(False),
):
    return await ingest_upload(
        file=file,
        source=source,
        author=author,
        doc_type=doc_type,
        entity_name=entity_name,
        entity_type=entity_type,
        entity_aliases=entity_aliases,
        confirmation_token=confirmation_token,
        entity_confirmed=entity_confirmed,
        entity_id=entity_id,
        create_new_entity=create_new_entity,
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
        return build_review_response(result, interrupt_data, thread_id)

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
        return build_review_response(result, interrupt_data, thread_id)

    return await build_done_response(result, thread_id)

@app.post("/generate/resume")
async def resume_review(payload: ResumeRequest):
    workflow = get_workflow()
    config = {"configurable": {"thread_id": payload.thread_id}}

    try:
        resume_value: Any = payload.feedback
        if payload.entity_confirmed is not None or payload.entity_name is not None:
            resume_value = {
                "confirmed": payload.entity_confirmed is True,
                "entity_name": (payload.entity_name or "").strip(),
                "entity_id": payload.entity_id,
                "create_new_entity": payload.create_new_entity,
            }
        result = workflow.invoke(Command(resume=resume_value), config=config)
    except GuardValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    interrupt_data = extract_interrupt(result)
    if interrupt_data:
        return build_review_response(result, interrupt_data, payload.thread_id)

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


@app.get("/entities")
def list_entities():
    with spine_pool.connection() as conn:
        rows = conn.execute(
            "SELECT id, display_name, aliases FROM entities ORDER BY display_name ASC"
        ).fetchall()
    return [
        {"id": str(row[0]), "name": row[1], "aliases": row[2] or []}
        for row in rows
    ]


@app.get("/dashboard/stats")
def dashboard_stats(entity_id: Optional[str] = None):
    if entity_id is not None:
        try:
            uuid.UUID(entity_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="entity_id must be a valid UUID")

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = month_start
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    since_30d = now - timedelta(days=30)
    since_90d = now - timedelta(days=90)
    trend_start = week_start - timedelta(weeks=3)

    # "Flagged" incident tasks are the ones the risk & escalation agent (a2)
    # created via the triggered_by link — this excludes plain document text
    # that the ingestion classifier happens to label 'incident'.
    flagged_incident_join = """
        FROM records r
        JOIN links l ON l.from_record_id = r.id AND l.link_type = 'triggered_by'
        WHERE r.record_type = 'incident'
    """
    entity_clause = "AND r.entity_id = %(entity_id)s::uuid" if entity_id else ""
    entity_params: dict[str, Any] = {"entity_id": entity_id} if entity_id else {}

    with spine_pool.connection() as conn:
        open_tasks = conn.execute(
            f"SELECT count(*) {flagged_incident_join} AND r.status = 'draft' {entity_clause}",
            entity_params,
        ).fetchone()[0]

        incidents_this_month = conn.execute(
            f"SELECT count(*) {flagged_incident_join} AND r.created_at >= %(since)s {entity_clause}",
            {"since": month_start, **entity_params},
        ).fetchone()[0]

        incidents_last_month = conn.execute(
            f"SELECT count(*) {flagged_incident_join} AND r.created_at >= %(start)s AND r.created_at < %(end)s {entity_clause}",
            {"start": last_month_start, "end": last_month_end, **entity_params},
        ).fetchone()[0]

        tasks_pending_this_week = conn.execute(
            f"SELECT count(*) {flagged_incident_join} AND r.status = 'draft' AND r.created_at >= %(since)s {entity_clause}",
            {"since": week_start, **entity_params},
        ).fetchone()[0]

        notes_completed_this_week = conn.execute(
            f"SELECT count(*) FROM records r WHERE record_type = 'note' AND created_at >= %(since)s {entity_clause}",
            {"since": week_start, **entity_params},
        ).fetchone()[0]

        if entity_id:
            documents_ingested_this_week = conn.execute(
                """
                SELECT count(distinct d.id)
                FROM documents d
                JOIN entity_documents ed ON ed.document_id = d.id
                WHERE d.created_at >= %(since)s AND ed.entity_id = %(entity_id)s::uuid
                """,
                {"since": week_start, **entity_params},
            ).fetchone()[0]
        else:
            documents_ingested_this_week = conn.execute(
                "SELECT count(*) FROM documents WHERE created_at >= %(since)s",
                {"since": week_start},
            ).fetchone()[0]

        def incidents_by_category(since: datetime) -> list[dict[str, Any]]:
            rows = conn.execute(
                f"""
                SELECT coalesce(r.body->>'trigger_id', 'uncategorised') AS category, count(*)
                {flagged_incident_join} AND r.created_at >= %(since)s {entity_clause}
                GROUP BY category
                ORDER BY count(*) DESC
                """,
                {"since": since, **entity_params},
            ).fetchall()
            return [{"category": row[0], "count": int(row[1])} for row in rows]

        notes_trend_rows = conn.execute(
            f"""
            SELECT date_trunc('week', created_at) AS week_start, count(*)
            FROM records r
            WHERE record_type = 'note' AND created_at >= %(since)s {entity_clause}
            GROUP BY week_start
            ORDER BY week_start
            """,
            {"since": trend_start, **entity_params},
        ).fetchall()

        recent_rows = conn.execute(
            f"""
            SELECT r.id, r.body, r.status, r.created_at, e.display_name
            FROM records r
            JOIN links l ON l.from_record_id = r.id AND l.link_type = 'triggered_by'
            LEFT JOIN entities e ON e.id = r.entity_id
            WHERE r.record_type = 'incident' {entity_clause}
            ORDER BY r.created_at DESC
            LIMIT 10
            """,
            entity_params,
        ).fetchall()

    notes_trend = []
    trend_by_week = {row[0].date().isoformat(): int(row[1]) for row in notes_trend_rows}
    for i in range(4):
        week = (trend_start + timedelta(weeks=i)).date().isoformat()
        notes_trend.append({"week_start": week, "count": trend_by_week.get(week, 0)})

    recent_flagged_tasks = []
    for row in recent_rows:
        body = row[1] if isinstance(row[1], dict) else json.loads(row[1])
        recent_flagged_tasks.append(
            {
                "id": str(row[0]),
                "participant": row[4] or "Unknown participant",
                "category": body.get("trigger_id"),
                "created_at": row[3].isoformat(),
                "status": row[2],
            }
        )

    return {
        "open_tasks": int(open_tasks),
        "incidents_this_month": int(incidents_this_month),
        "incidents_last_month": int(incidents_last_month),
        "tasks_pending_this_week": int(tasks_pending_this_week),
        "notes_completed_this_week": int(notes_completed_this_week),
        "documents_ingested_this_week": int(documents_ingested_this_week),
        "incidents_by_category": {
            "30d": incidents_by_category(since_30d),
            "90d": incidents_by_category(since_90d),
        },
        "notes_trend": notes_trend,
        "recent_flagged_tasks": recent_flagged_tasks,
    }
