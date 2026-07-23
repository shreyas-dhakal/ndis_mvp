import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import { api } from "../lib/api.js";

function SourceList({ sources, onOpen }) {
  if (!sources?.length) return null;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="mt-3 inline-flex items-center gap-2 rounded-full border border-teal-100 bg-white/70 px-2.5 py-1.5 text-[11px] font-medium text-teal-700 transition-colors hover:border-teal-400 hover:bg-white"
      aria-label={`Show ${sources.length} citation${sources.length === 1 ? "" : "s"}`}
    >
      <span className="flex h-4 w-4 items-center justify-center rounded-full bg-teal-100 text-[10px] font-semibold text-teal-700">
        {sources.length}
      </span>
      <span>Show {sources.length === 1 ? "citation" : "citations"}</span>
      <span aria-hidden="true" className="text-sm leading-none">↗</span>
    </button>
  );
}

function CitationPanel({ sources, onClose }) {
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <>
      <button
        type="button"
        onClick={onClose}
        className="absolute inset-0 z-10 cursor-default bg-ink/10 xl:hidden"
        aria-label="Close citations"
      />
      <aside
        className="absolute right-0 top-0 z-20 flex h-full w-full max-w-[390px] flex-col border-l border-line bg-[#f8f8f4] shadow-[-14px_0_35px_rgba(29,42,45,.10)]"
        aria-label="Citations"
      >
        <div className="flex items-start justify-between border-b border-line px-5 py-4">
          <div>
            <div className="eyebrow">Answer references</div>
            <h2 className="mt-1 font-display text-lg font-semibold text-ink">Citations</h2>
            <p className="mt-1 text-xs text-slate">The files and records used for this answer.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="icon-button text-lg leading-none"
            aria-label="Close citations"
          >
            ×
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          {sources.map((source, index) => (
            <article key={source.chunk_id || `${source.citation?.document_id}-${index}`} className="rounded-xl border border-line bg-white px-3.5 py-3 text-xs text-slate shadow-sm">
              <div className="flex items-start gap-2 font-medium text-ink">
                <span className="rounded bg-teal-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-teal-700">
                  {source.citation?.label || "Source"}
                </span>
                <span className="leading-5">{source.citation?.record_title || source.record_type}</span>
              </div>
              <div className="mt-2 border-b border-line pb-2 text-[11px] text-slate/80">
                {source.citation?.document_name || source.citation?.document_id || "Unknown document"}
                {source.citation?.page_number ? ` • Page ${source.citation.page_number}` : ""}
                {source.citation?.section ? ` • ${source.citation.section}` : ""}
              </div>
              <p className="mt-2 leading-5">{source.snippet || source.text}</p>
            </article>
          ))}
        </div>
      </aside>
    </>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);
  const [openSources, setOpenSources] = useState(null);

  const send = async () => {
    if (!input.trim() || sending) return;
    const question = input.trim();
    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setSending(true);
    setError(null);
    try {
      const data = await api.post("/chat", { question });
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          text: data.answer,
          sources: data.retrieved_chunks || [],
        },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="relative flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="font-display text-2xl font-semibold mb-1">Ask Caseload AI</h1>
      <p className="text-slate text-sm mb-6">
        Ask a question about a person, a goal, or one of your files.
      </p>

      <div className="flex-1 border border-line rounded-md bg-white/40 p-4 overflow-y-auto space-y-3">
        {!messages.length && (
          <p className="text-sm text-slate italic">
            Start with a question like “What goals did we work on with Sam last month?”
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[75%] px-3 py-2 rounded-md text-sm ${
              m.role === "user"
                ? "bg-teal-500 text-white ml-auto"
                : "bg-teal-50 text-ink"
            }`}
          >
            {m.role === "assistant" ? (
              <div className="markdown-body">
                <ReactMarkdown>{m.text}</ReactMarkdown>
              </div>
            ) : (
              <div>{m.text}</div>
            )}
            {m.role === "assistant" && (
              <SourceList sources={m.sources} onOpen={() => setOpenSources(m.sources)} />
            )}
          </div>
        ))}
      </div>

      {openSources && (
        <CitationPanel sources={openSources} onClose={() => setOpenSources(null)} />
      )}

      {error && <p className="text-xs text-ochre-600 mt-2">{error}</p>}

      <div className="flex gap-2 mt-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="What would you like to find out?"
          className="flex-1 border border-line rounded-md px-3 py-2.5 text-sm focus:border-teal-500 outline-none"
        />
        <button
          onClick={send}
          disabled={sending}
          className="px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 disabled:opacity-50 transition-colors"
        >
          {sending ? "Thinking…" : "Ask"}
        </button>
      </div>
    </div>
  );
}
