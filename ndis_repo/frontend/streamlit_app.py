import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
import streamlit as st

import html
import re
from datetime import datetime

from app.core.config import LOG_DIR, LOG_LEVEL
from app.core.logging_setup import setup_logging

setup_logging(
    log_dir=LOG_DIR,
    activity_name=os.getenv("ACTIVITY_NAME")
    or f"streamlit_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    log_level=LOG_LEVEL,
)

RECORD_TYPES = ["note", "incident", "consent", "plan", "goal", "generic"]


def _highlight_snippet(snippet: str, terms: list[str]) -> str:
    """Return HTML with <mark> highlights for literal terms (best-effort)."""

    if not snippet:
        return ""
    clean_terms = [
        t
        for t in (terms or [])
        if isinstance(t, str) and t.strip() and len(t.strip()) >= 3
    ]
    if not clean_terms:
        return html.escape(snippet)

    # Prefer longer terms first to reduce partial overlaps.
    clean_terms = sorted({t.lower() for t in clean_terms}, key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(t) for t in clean_terms) + ")", flags=re.IGNORECASE
    )

    out: list[str] = []
    last = 0
    for m in pattern.finditer(snippet):
        out.append(html.escape(snippet[last : m.start()]))
        out.append(f"<mark>{html.escape(snippet[m.start() : m.end()])}</mark>")
        last = m.end()
    out.append(html.escape(snippet[last:]))
    return "".join(out)


def _response_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return resp.text.strip() or resp.reason_phrase

    detail = payload.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail.strip()
    return resp.text.strip() or resp.reason_phrase


def _get_backend_base_url() -> str:
    return st.sidebar.text_input("Backend base URL", "http://localhost:8000").rstrip(
        "/"
    )


def ingest_file(
    *,
    backend_base_url: str,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    source: str,
    author: str,
    doc_type: str,
) -> dict:
    url = f"{backend_base_url}/ingest/file"
    data = {"source": source, "author": author, "doc_type": doc_type}
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}

    try:
        with httpx.Client(timeout=300) as client:
            resp = client.post(url, data=data, files=files)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(
            f"Ingest failed ({exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not reach backend at {backend_base_url}: {exc}"
        ) from exc


def retrieve(
    *,
    backend_base_url: str,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    alpha: float,
) -> list[dict]:
    url = f"{backend_base_url}/retrieve"
    payload = {
        "query": query,
        "top_k": top_k,
        "source_filter": source_filter,
        "record_type": record_type,
        "alpha": alpha,
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(
            f"Retrieve failed ({exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not reach backend at {backend_base_url}: {exc}"
        ) from exc


def agent_answer(
    *,
    backend_base_url: str,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    alpha: float,
    context_mode: str,
) -> dict:
    url = f"{backend_base_url}/agent/answer"
    payload = {
        "query": query,
        "top_k": top_k,
        "source_filter": source_filter,
        "record_type": record_type,
        "alpha": alpha,
        "context_mode": context_mode,
    }

    try:
        with httpx.Client(timeout=180) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(
            f"Agent failed ({exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not reach backend at {backend_base_url}: {exc}"
        ) from exc


def list_documents(*, backend_base_url: str) -> list[dict]:
    url = f"{backend_base_url}/documents"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(
            f"List documents failed ({exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not reach backend at {backend_base_url}: {exc}"
        ) from exc


def delete_document(*, backend_base_url: str, document_id: int) -> None:
    url = f"{backend_base_url}/documents/{document_id}"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.delete(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(
            f"Delete failed ({exc.response.status_code}): {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not reach backend at {backend_base_url}: {exc}"
        ) from exc


def main() -> None:
    st.set_page_config(page_title="NDIS RAG", layout="wide")
    st.title("NDIS RAG (Ingest + Retrieve)")
    st.caption(
        "Uploads documents, chunks+embeds them, then retrieves relevant chunks with citations."
    )

    backend_base_url = _get_backend_base_url()

    st.sidebar.header("Ingest")
    uploaded = st.sidebar.file_uploader(
        "Document file",
        type=["pdf", "docx", "csv", "txt"],
        accept_multiple_files=False,
    )
    source = st.sidebar.text_input("source", value="local")
    author = st.sidebar.text_input("author", value="user")
    doc_type = st.sidebar.text_input("doc_type", value="document")

    if st.sidebar.button("Ingest file", disabled=uploaded is None):
        with st.spinner("Parsing + embedding + storing..."):
            try:
                result = ingest_file(
                    backend_base_url=backend_base_url,
                    file_bytes=uploaded.getvalue(),
                    filename=uploaded.name,
                    content_type=uploaded.type,
                    source=source,
                    author=author,
                    doc_type=doc_type,
                )
            except RuntimeError as exc:
                st.sidebar.error(str(exc))
            else:
                st.sidebar.success(
                    f"Ingested document_id={result['document_id']} "
                    f"({result['records_created']} records, {result['chunks_created']} chunks)"
                )

    st.sidebar.header("Retrieve")
    use_agent = st.sidebar.checkbox("Use Qwen agent (grounded)", value=True)
    send_full_text = st.sidebar.checkbox(
        "Send full chunk text to LLM (instead of snippet)", value=False
    )
    top_k = st.sidebar.slider("top_k", min_value=1, max_value=20, value=4)
    alpha = st.sidebar.slider(
        "alpha (semantic weight)", min_value=0.0, max_value=1.0, value=0.55, step=0.05
    )
    source_filter = st.sidebar.text_input("source_filter (optional)", value="")
    record_type = st.sidebar.selectbox(
        "record_type (optional)",
        options=["", *RECORD_TYPES],
        index=0,
        format_func=lambda x: "(any)" if x == "" else x,
    )

    source_filter_v = source_filter.strip() or None
    record_type_v = record_type.strip() or None

    st.sidebar.header("Documents")
    if "documents_cache" not in st.session_state:
        st.session_state.documents_cache = []

    if st.sidebar.button("Retrieve all documents"):
        try:
            st.session_state.documents_cache = list_documents(
                backend_base_url=backend_base_url
            )
        except RuntimeError as exc:
            st.sidebar.error(str(exc))

    docs = st.session_state.documents_cache
    if docs:
        with st.sidebar.expander("Stored documents", expanded=False):
            for d in docs:
                doc_id = d.get("document_id")
                filename = d.get("original_filename") or "(unknown)"
                chunks_count = d.get("chunks_count")
                st.markdown(
                    f"**{doc_id}** · {filename}\n"
                    f"Records: {d.get('records_count')} · Chunks: {chunks_count}"
                )
                if st.button(
                    f"Delete {doc_id}",
                    key=f"delete-doc-{doc_id}",
                    type="secondary",
                ):
                    try:
                        delete_document(
                            backend_base_url=backend_base_url, document_id=int(doc_id)
                        )
                    except RuntimeError as exc:
                        st.sidebar.error(str(exc))
                    else:
                        st.sidebar.success(f"Deleted document {doc_id}")
                        st.session_state.documents_cache = list_documents(
                            backend_base_url=backend_base_url
                        )

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("chunks"):
                with st.expander("Retrieved chunks", expanded=False):
                    for i, c in enumerate(msg["chunks"], start=1):
                        citation = c.get("citation") or {}
                        snippet = c.get("snippet") or ""
                        highlights = c.get("highlights") or []
                        st.markdown(
                            f"**{i}. score={c.get('score')}** · record_type={c.get('record_type')}"
                            f" · document_id={citation.get('document_id')}"
                        )
                        if citation.get("record_title"):
                            st.markdown(f"Title: `{citation.get('record_title')}`")
                        if citation.get("provenance_pointer"):
                            st.markdown(
                                f"Provenance: `{citation.get('provenance_pointer')}`"
                            )
                        if citation.get("section"):
                            st.markdown(f"Section: `{citation.get('section')}`")

                        if snippet:
                            st.markdown(
                                _highlight_snippet(snippet, highlights),
                                unsafe_allow_html=True,
                            )

                        with st.expander("Show evidence", expanded=False):
                            st.code(c.get("text", ""), language="text")

    query = st.chat_input("Ask a question")
    if query:
        st.session_state.messages.append({"role": "user", "content": query})
        st.chat_message("user").markdown(query)

        with st.chat_message("assistant"):
            chunks: list[dict] = []
            assistant_content = ""
            if use_agent:
                with st.spinner("Answering with grounded agent..."):
                    try:
                        context_mode = "full" if send_full_text else "snippet"
                        resp = agent_answer(
                            backend_base_url=backend_base_url,
                            query=query,
                            top_k=top_k,
                            source_filter=source_filter_v,
                            record_type=record_type_v,
                            alpha=alpha,
                            context_mode=context_mode,
                        )
                    except RuntimeError as exc:
                        st.error(str(exc))
                    else:
                        assistant_content = resp.get("answer", "")
                        st.markdown(assistant_content)
                        chunks = resp.get("retrieved_chunks") or []
            else:
                with st.spinner("Retrieving..."):
                    try:
                        chunks = retrieve(
                            backend_base_url=backend_base_url,
                            query=query,
                            top_k=top_k,
                            source_filter=source_filter_v,
                            record_type=record_type_v,
                            alpha=alpha,
                        )
                    except RuntimeError as exc:
                        st.error(str(exc))
                        chunks = []
                    else:
                        assistant_content = f"Retrieved {len(chunks)} relevant chunks."
                        st.markdown(assistant_content)

            if chunks:
                with st.expander("Retrieved chunks", expanded=False):
                    for i, c in enumerate(chunks, start=1):
                        citation = c.get("citation") or {}
                        snippet = c.get("snippet") or ""
                        highlights = c.get("highlights") or []
                        st.markdown(
                            f"**{i}. score={c.get('score')}** · record_type={c.get('record_type')}"
                            f" · document_id={citation.get('document_id')}"
                        )
                        if citation.get("record_title"):
                            st.markdown(f"Title: `{citation.get('record_title')}`")
                        if citation.get("provenance_pointer"):
                            st.markdown(
                                f"Provenance: `{citation.get('provenance_pointer')}`"
                            )
                        if citation.get("section"):
                            st.markdown(f"Section: `{citation.get('section')}`")

                        if snippet:
                            st.markdown(
                                _highlight_snippet(snippet, highlights),
                                unsafe_allow_html=True,
                            )

                        with st.expander("Show evidence", expanded=False):
                            st.code(c.get("text", ""), language="text")

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": assistant_content or ("(no answer)" if use_agent else ""),
                "chunks": chunks if chunks else None,
            }
        )


if __name__ == "__main__":
    main()
