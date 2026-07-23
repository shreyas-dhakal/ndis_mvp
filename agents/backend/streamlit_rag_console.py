import html
import re

import httpx
import streamlit as st


RECORD_TYPES = ["note", "incident", "consent", "plan", "goal", "generic"]


def _highlight_snippet(snippet: str, terms: list[str]) -> str:
    if not snippet:
        return ""

    clean_terms = [
        term
        for term in (terms or [])
        if isinstance(term, str) and term.strip() and len(term.strip()) >= 3
    ]
    if not clean_terms:
        return html.escape(snippet)

    clean_terms = sorted({term.lower() for term in clean_terms}, key=len, reverse=True)
    pattern = re.compile(
        "(" + "|".join(re.escape(term) for term in clean_terms) + ")",
        flags=re.IGNORECASE,
    )

    out: list[str] = []
    last = 0
    for match in pattern.finditer(snippet):
        out.append(html.escape(snippet[last : match.start()]))
        out.append(f"<mark>{html.escape(snippet[match.start() : match.end()])}</mark>")
        last = match.end()
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


def _backend_base_url() -> str:
    return st.sidebar.text_input("Backend base URL", "http://localhost:8000").rstrip("/")


def ingest_file(
    *,
    backend_base_url: str,
    file_bytes: bytes,
    filename: str,
    content_type: str | None,
    source: str,
    author: str,
    doc_type: str,
    entity_name: str | None,
    entity_aliases: str | None,
) -> dict:
    url = f"{backend_base_url}/ingest/file"
    data = {
        "source": source,
        "author": author,
        "doc_type": doc_type,
        "entity_name": entity_name or "",
        "entity_aliases": entity_aliases or "",
    }
    files = {"file": (filename, file_bytes, content_type or "application/octet-stream")}

    try:
        with httpx.Client(timeout=300) as client:
            resp = client.post(url, data=data, files=files)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(f"Ingest failed ({exc.response.status_code}): {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach backend at {backend_base_url}: {exc}") from exc


def retrieve(
    *,
    backend_base_url: str,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    entity_name: str | None,
    alpha: float,
) -> list[dict]:
    url = f"{backend_base_url}/retrieve"
    payload = {
        "query": query,
        "top_k": top_k,
        "source_filter": source_filter,
        "record_type": record_type,
        "entity_name": entity_name,
        "alpha": alpha,
    }

    try:
        with httpx.Client(timeout=120) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(f"Retrieve failed ({exc.response.status_code}): {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach backend at {backend_base_url}: {exc}") from exc


def agent_answer(
    *,
    backend_base_url: str,
    query: str,
    top_k: int,
    source_filter: str | None,
    record_type: str | None,
    entity_name: str | None,
    alpha: float,
    context_mode: str,
) -> dict:
    url = f"{backend_base_url}/agent/answer"
    payload = {
        "query": query,
        "top_k": top_k,
        "source_filter": source_filter,
        "record_type": record_type,
        "entity_name": entity_name,
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
        raise RuntimeError(f"Agent failed ({exc.response.status_code}): {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach backend at {backend_base_url}: {exc}") from exc


def list_documents(*, backend_base_url: str) -> list[dict]:
    url = f"{backend_base_url}/documents"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(f"List documents failed ({exc.response.status_code}): {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach backend at {backend_base_url}: {exc}") from exc


def delete_document(*, backend_base_url: str, document_id: int) -> None:
    url = f"{backend_base_url}/documents/{document_id}"
    try:
        with httpx.Client(timeout=120) as client:
            resp = client.delete(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = _response_detail(exc.response)
        raise RuntimeError(f"Delete failed ({exc.response.status_code}): {detail}") from exc
    except httpx.RequestError as exc:
        raise RuntimeError(f"Could not reach backend at {backend_base_url}: {exc}") from exc


def main() -> None:
    st.set_page_config(page_title="NDIS RAG Console", layout="wide")
    st.title("NDIS RAG Console")
    st.caption(
        "Uploads documents, retrieves evidence, and runs grounded chat against the unified agents backend."
    )

    backend_base_url = _backend_base_url()

    st.sidebar.header("Ingest")
    uploaded = st.sidebar.file_uploader(
        "Document file",
        type=["pdf", "docx", "csv", "txt"],
        accept_multiple_files=False,
    )
    source = st.sidebar.text_input("Source", value="local")
    author = st.sidebar.text_input("Author", value="user")
    doc_type = st.sidebar.text_input("Doc type", value="document")
    entity_name = st.sidebar.text_input("Entity name", value="")
    entity_aliases = st.sidebar.text_input("Entity aliases", value="")
    if st.sidebar.button("Upload", use_container_width=True):
        if not uploaded:
            st.sidebar.error("Choose a file first.")
        else:
            with st.spinner("Uploading and ingesting..."):
                try:
                    result = ingest_file(
                        backend_base_url=backend_base_url,
                        file_bytes=uploaded.getvalue(),
                        filename=uploaded.name,
                        content_type=uploaded.type,
                        source=source,
                        author=author,
                        doc_type=doc_type,
                        entity_name=entity_name.strip() or None,
                        entity_aliases=entity_aliases.strip() or None,
                    )
                except RuntimeError as exc:
                    st.sidebar.error(str(exc))
                else:
                    st.sidebar.success(
                        f"Ingested {result['document']['filename']} ({result['records_created']} records, {result['chunks_created']} chunks)"
                    )

    st.sidebar.header("Chat")
    top_k = st.sidebar.slider("Top K", min_value=1, max_value=12, value=4)
    alpha = st.sidebar.slider("Semantic weight", min_value=0.0, max_value=1.0, value=0.55)
    source_filter_v = st.sidebar.text_input("Source filter", value="").strip() or None
    record_type_v = st.sidebar.selectbox("Record type", [""] + RECORD_TYPES, index=0) or None
    entity_filter_v = st.sidebar.text_input("Entity filter", value="").strip() or None
    use_agent = st.sidebar.checkbox("Use grounded agent", value=True)
    send_full_text = st.sidebar.checkbox("Send full chunk text to LLM", value=True)

    if "messages" not in st.session_state:
        st.session_state.messages = []

    col_docs, col_chat = st.columns([1, 2])

    with col_docs:
        st.subheader("Documents")
        try:
            docs = list_documents(backend_base_url=backend_base_url)
        except RuntimeError as exc:
            st.error(str(exc))
            docs = []

        if not docs:
            st.info("No documents ingested yet.")
        else:
            for doc in docs:
                docs_col, delete_col = st.columns([5, 1])
                with docs_col:
                    st.markdown(f"**{doc.get('filename')}**")
                    st.caption(
                        f"Records: {doc.get('records_count')} | Chunks: {doc.get('chunks_count')} | Source: {doc.get('source')}"
                    )
                with delete_col:
                    if st.button("Delete", key=f"delete_{doc['document_id']}"):
                        try:
                            delete_document(
                                backend_base_url=backend_base_url,
                                document_id=doc["document_id"],
                            )
                        except RuntimeError as exc:
                            st.error(str(exc))
                        else:
                            st.rerun()

    with col_chat:
        st.subheader("Chat")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg.get("chunks"):
                    with st.expander("Retrieved chunks", expanded=False):
                        for index, chunk in enumerate(msg["chunks"], start=1):
                            citation = chunk.get("citation") or {}
                            snippet = chunk.get("snippet") or ""
                            highlights = chunk.get("highlights") or []
                            st.markdown(
                                f"**Chunk {index}** | score={chunk.get('score')} | doc={citation.get('document_id')}"
                            )
                            st.caption(
                                f"section={citation.get('section')} | title={citation.get('record_title')}"
                            )
                            if snippet:
                                st.markdown(
                                    _highlight_snippet(snippet, highlights),
                                    unsafe_allow_html=True,
                                )
                            with st.expander("Show evidence", expanded=False):
                                st.code(chunk.get("text", ""), language="text")

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
                                entity_name=entity_filter_v,
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
                                entity_name=entity_filter_v,
                                alpha=alpha,
                            )
                        except RuntimeError as exc:
                            st.error(str(exc))
                        else:
                            assistant_content = f"Retrieved {len(chunks)} relevant chunks."
                            st.markdown(assistant_content)

                if chunks:
                    with st.expander("Retrieved chunks", expanded=False):
                        for index, chunk in enumerate(chunks, start=1):
                            citation = chunk.get("citation") or {}
                            snippet = chunk.get("snippet") or ""
                            highlights = chunk.get("highlights") or []
                            st.markdown(
                                f"**Chunk {index}** | score={chunk.get('score')} | doc={citation.get('document_id')}"
                            )
                            st.caption(
                                f"section={citation.get('section')} | title={citation.get('record_title')}"
                            )
                            if snippet:
                                st.markdown(
                                    _highlight_snippet(snippet, highlights),
                                    unsafe_allow_html=True,
                                )
                            with st.expander("Show evidence", expanded=False):
                                st.code(chunk.get("text", ""), language="text")

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": assistant_content or "(no answer)",
                        "chunks": chunks if chunks else None,
                    }
                )


if __name__ == "__main__":
    main()
