import streamlit as st
import requests
from datetime import datetime, timezone

st.set_page_config(page_title="NDIS Progress Note Generator", layout="wide")

BACKEND_URL = "http://localhost:8000"

for key, default in [
    ("thread_id", None), ("status", "idle"), ("current_note", None),
    ("pdf_path", None), ("a2_task_created", False), ("a2_trigger_id", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def handle_response(res):
    if res.status_code == 200:
        data = res.json()
        st.session_state.thread_id = data.get("thread_id", st.session_state.thread_id)
        st.session_state.status = data["status"]
        st.session_state.current_note = data.get("note")
        st.session_state.pdf_path = data.get("pdf_path")
        st.session_state.a2_task_created = data.get("a2_task_created", False)
        st.session_state.a2_trigger_id = data.get("a2_trigger_id")
        st.rerun()
    else:
        try:
            detail = res.json().get("detail", res.text)
        except Exception:
            detail = res.text
        st.error(f"Backend error ({res.status_code}): {detail}")


def render_note_generator():
    if st.session_state.status == "idle":
        mode = st.radio("Choose input method", ["Text Transcript", "Upload Audio"], horizontal=True)

        if mode == "Text Transcript":
            transcript = st.text_area("Paste conversation transcript here", height=300)
            if st.button("Generate Progress Note", type="primary"):
                if not transcript.strip():
                    st.error("Please enter a transcript")
                else:
                    with st.spinner("Generating NDIS Progress Note..."):
                        try:
                            res = requests.post(f"{BACKEND_URL}/generate/text", json={"transcript": transcript})
                            handle_response(res)
                        except requests.exceptions.RequestException as e:
                            st.error(f"Could not reach backend: {e}")
        else:
            audio_file = st.file_uploader("Upload audio recording", type=["mp3", "wav", "m4a", "ogg"])
            whisper_size = st.selectbox("Whisper Model Size", ["small", "medium", "large-v3"], index=0)
            if st.button("Transcribe & Generate Note", type="primary"):
                if not audio_file:
                    st.error("Please upload audio file")
                else:
                    with st.spinner("Transcribing and generating note... (this may take a minute)"):
                        try:
                            files = {"file": (audio_file.name, audio_file.getvalue())}
                            data = {"whisper_model_size": whisper_size}
                            res = requests.post(f"{BACKEND_URL}/generate/audio", files=files, data=data)
                            handle_response(res)
                        except requests.exceptions.RequestException as e:
                            st.error(f"Could not reach backend: {e}")

    elif st.session_state.status == "awaiting_review":
        st.subheader("Review NDIS Progress Note")
        note = st.session_state.current_note

        if not note:
            st.error("No note data available. Please start over.")
            if st.button("Start Over"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Subjective**")
                st.info(note.get("subjective") or "Not documented")
                st.markdown("**Objective**")
                st.info(note.get("objective") or "Not documented")
                st.markdown("**Assessment**")
                st.info(note.get("assessment") or "Not documented")
                st.markdown("**Plan**")
                st.info(note.get("plan") or "Not documented")
            with col2:
                st.markdown("**Participant Voice**")
                st.info(note.get("participant_voice") or "Not documented")
                st.markdown("**Support Type**")
                st.info(note.get("support_type") or "Not documented")
                st.markdown("**Risks / Incidents**")
                st.info(note.get("risks_incidents") or "Not documented")
                st.markdown("**Consent Noted**")
                consent = note.get("consent_noted")
                st.info("Yes" if consent is True else "No" if consent is False else "Not documented")

            st.markdown("**Linked Goals**")
            goals = note.get("linked_goals") or []
            st.write(goals if goals else "None linked")

            st.divider()

            col_a, col_b = st.columns([1, 3])
            with col_a:
                if st.button("Approve & Generate PDF", type="primary"):
                    with st.spinner("Finalizing note..."):
                        try:
                            res = requests.post(
                                f"{BACKEND_URL}/generate/resume",
                                json={"thread_id": st.session_state.thread_id, "feedback": "yes"}
                            )
                            handle_response(res)
                        except requests.exceptions.RequestException as e:
                            st.error(f"Could not reach backend: {e}")
            with col_b:
                feedback = st.text_input(
                    "Or describe changes you'd like",
                    placeholder="e.g. Add more detail to the plan section"
                )
                if st.button("Submit Feedback"):
                    if not feedback.strip():
                        st.error("Please describe the changes, or use Approve above.")
                    else:
                        with st.spinner("Revising note..."):
                            try:
                                res = requests.post(
                                    f"{BACKEND_URL}/generate/resume",
                                    json={"thread_id": st.session_state.thread_id, "feedback": feedback}
                                )
                                handle_response(res)
                            except requests.exceptions.RequestException as e:
                                st.error(f"Could not reach backend: {e}")

    elif st.session_state.status == "done":
        st.success("NDIS Progress Note Approved!")

        # A2 ran automatically when the note was approved - surface the
        # result right here so the support worker sees it immediately,
        # not just buried in the task queue tab.
        if st.session_state.a2_task_created:
            st.warning(
                f"This note triggered a reportable-incident check: "
                f"**{st.session_state.a2_trigger_id.replace('_', ' ').title()}**. "
                f"A task has been created — see the Task Queue tab."
            )

        if st.session_state.pdf_path:
            try:
                res = requests.get(f"{BACKEND_URL}/download/pdf", params={"path": st.session_state.pdf_path})
                if res.status_code == 200:
                    st.download_button(
                        label="Download PDF Progress Note",
                        data=res.content,
                        file_name="NDIS_Progress_Note.pdf",
                        mime="application/pdf"
                    )
                else:
                    st.error(f"Could not fetch PDF ({res.status_code}): {res.text}")
            except requests.exceptions.RequestException as e:
                st.error(f"Could not download PDF: {e}")
        else:
            st.warning("No PDF path was returned by the backend.")

        if st.button("Start New Note"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


def format_time_left(deadline_str: str) -> tuple[str, str]:
    deadline = datetime.fromisoformat(deadline_str)
    remaining = deadline - datetime.now(timezone.utc)
    hours_left = remaining.total_seconds() / 3600
    if hours_left < 0:
        return "OVERDUE", "red"
    elif hours_left < 4:
        return f"{hours_left:.1f}h left", "red"
    elif hours_left < 24:
        return f"{hours_left:.1f}h left", "orange"
    else:
        return f"{hours_left / 24:.1f}d left", "green"


def render_task_queue():
    st.subheader("Task Queue")
    sub_tab_review, sub_tab_confirmed = st.tabs(["Needs Review", "Confirmed — Pending Action"])
    with sub_tab_review:
        _render_task_list(view="pending", show_approve_dismiss=True)
    with sub_tab_confirmed:
        _render_task_list(view="confirmed", show_approve_dismiss=False)


def _render_task_list(view: str, show_approve_dismiss: bool):
    try:
        res = requests.get(f"{BACKEND_URL}/tasks", params={"view": view})
    except requests.exceptions.RequestException as e:
        st.error(f"Could not reach backend: {e}")
        return
    if res.status_code != 200:
        st.error(f"Backend error ({res.status_code}): {res.text}")
        return

    tasks = res.json()["tasks"]
    if not tasks:
        st.info("Nothing here.")
        return

    for task in tasks:
        time_left, color = format_time_left(task["deadline"])
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{task['trigger_id'].replace('_', ' ').title()}**")
                created = datetime.fromisoformat(task["created_at"])
                st.caption(f"From note logged {created.strftime('%b %d, %I:%M %p')}")
            with col2:
                st.markdown(f":{color}[**{time_left}**]")
            st.write(f"Matched on: _{task['reasoning']}_")

            if show_approve_dismiss:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("Approve", key=f"approve_{task['id']}", type="primary"):
                        requests.post(f"{BACKEND_URL}/tasks/{task['id']}/approve",
                                      json={"reviewer": "streamlit_user"})
                        st.rerun()
                with btn_col2:
                    if st.button("Dismiss", key=f"dismiss_{task['id']}"):
                        st.session_state[f"dismissing_{task['id']}"] = True
                if st.session_state.get(f"dismissing_{task['id']}"):
                    reason = st.text_input("Why dismiss this?", key=f"reason_{task['id']}")
                    if st.button("Confirm dismiss", key=f"confirm_dismiss_{task['id']}"):
                        requests.post(f"{BACKEND_URL}/tasks/{task['id']}/dismiss",
                                      json={"reviewer": "streamlit_user", "reason": reason})
                        st.rerun()
            else:
                if st.button("Mark as Actioned", key=f"action_{task['id']}", type="primary"):
                    requests.post(f"{BACKEND_URL}/tasks/{task['id']}/action",
                                  json={"reviewer": "streamlit_user"})
                    st.rerun()


st.title("NDIS Progress Note Generator")
tab_generate, tab_tasks = st.tabs(["Generate Note", "Task Queue"])

with tab_generate:
    render_note_generator()

with tab_tasks:
    render_task_queue()