import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal, Optional, TypedDict

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

from langgraph.graph import END, START, StateGraph

from .local_llm import invoke_structured

load_dotenv()

taxomony_path = Path(__file__).resolve().parent / "taxomony.yaml"

conn_string = os.getenv("DATABASE_URL")
if not conn_string:
    print("Please add the db url key in .env")
else:
    print("DB url loaded successfullty")


class DecisionOutput(BaseModel):
    trigger_id: Optional[str] = None
    task_result: bool
    evidence: str


class ClassifierAgent(TypedDict):
    note: dict
    decision: DecisionOutput
    record_id: str
    record_timestamp: str
    conn_pool: object
    workflow_id: Optional[str]


graph = StateGraph(ClassifierAgent)


def load_taxonomy() -> list[dict]:
    with open(taxomony_path) as f:
        return yaml.safe_load(f)["triggers"]


def build_classification_prompt(taxonomy: list[dict], note: dict) -> str:
    trigger_block = "\n\n".join(
        f"id: {item['id']}\n"
        f"description: {item['description'].strip()}\n"
        f"positive examples: {item.get('examples_positive', [])}\n"
        f"negative examples: {item.get('examples_negative', [])}"
        for item in taxonomy
    )

    return f"""You are checking one NDIS support note against a fixed list of
reportable triggers. Only set task_result=true if the note clearly satisfies
a trigger's description, judged against its examples. If ambiguous, set
task_result=false rather than guessing. If task_result is false, leave
trigger_id as null.

Triggers:
{trigger_block}

Note to classify (JSON):
{json.dumps(note)}
"""


def make_decision(state: ClassifierAgent):
    note = state.get("note")
    taxonomy = load_taxonomy()
    prompt = build_classification_prompt(taxonomy, note)
    result = invoke_structured(
        DecisionOutput,
        system_prompt=(
            "You classify NDIS notes against a fixed trigger taxonomy. "
            "Be conservative. If the note is ambiguous, set task_result to false and trigger_id to null."
        ),
        user_prompt=prompt,
    )
    return {"decision": result}


def create_task(state: ClassifierAgent) -> dict:
    taxonomy = load_taxonomy()
    decision = state["decision"]
    trigger_def = next(item for item in taxonomy if item["id"] == decision.trigger_id)

    note_time = datetime.fromisoformat(state["record_timestamp"])
    deadline = note_time + timedelta(hours=trigger_def["deadline_hours"])

    conn_pool = state["conn_pool"]
    with conn_pool.connection() as conn:
        workflow_id = conn.execute(
            """
            INSERT INTO records (record_type, status, body, source, author)
            VALUES ('incident', 'draft', %(body)s, %(source)s, 'a2_agent')
            RETURNING id
            """,
            {
                "body": json.dumps(
                    {
                        "trigger_id": decision.trigger_id,
                        "reasoning": decision.evidence,
                        "workflow": trigger_def["workflow"],
                        "deadline": deadline.isoformat(),
                    }
                ),
                "source": f"a2:{state['record_id']}",
            },
        ).fetchone()[0]

        conn.execute(
            """
            INSERT INTO links (from_record_id, to_record_id, link_type)
            VALUES (%(from_id)s, %(to_id)s, 'triggered_by')
            """,
            {"from_id": str(workflow_id), "to_id": state["record_id"]},
        )
        conn.execute(
            """
            INSERT INTO events (actor, action, record_id, params)
            VALUES ('a2_agent', 'a2.trigger_matched', %(record_id)s, %(params)s)
            """,
            {
                "record_id": str(workflow_id),
                "params": json.dumps({"trigger_id": decision.trigger_id}),
            },
        )
        conn.commit()

    return {"workflow_id": str(workflow_id)}


def no_match(state: ClassifierAgent) -> dict:
    del state
    return {}


def check_decision(state: ClassifierAgent) -> Literal["create_task", "no_match"]:
    return "create_task" if state["decision"].task_result else "no_match"


def build_graph():
    graph = StateGraph(ClassifierAgent)
    graph.add_node("make_decision", make_decision)
    graph.add_node("create_task", create_task)

    graph.add_edge(START, "make_decision")
    graph.add_conditional_edges(
        "make_decision",
        check_decision,
        {"create_task": "create_task", "no_match": END},
    )
    graph.add_edge("create_task", END)
    return graph.compile()


workflow = None


def get_workflow():
    global workflow
    if workflow is None:
        workflow = build_graph()
    return workflow


def run_agent2(record_id: str, record_timestamp: str, note: dict, conn_pool) -> dict:
    wf = get_workflow()
    result = wf.invoke(
        {
            "note": note,
            "record_id": record_id,
            "record_timestamp": record_timestamp,
            "conn_pool": conn_pool,
        }
    )
    return {
        "decision": result["decision"].model_dump(),
        "workflow_id": result.get("workflow_id"),
    }
