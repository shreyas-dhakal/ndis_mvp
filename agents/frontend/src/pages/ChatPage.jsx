import { useState } from "react";
import { api } from "../lib/api.js";

function SourceList({ sources }) {
  if (!sources?.length) return null;

  return (
    <div className="mt-2 space-y-2 border-t border-teal-100 pt-2">
      {sources.map((source) => (
        <div key={source.chunk_id} className="rounded-md bg-white/80 px-3 py-2 text-xs text-slate">
          <div className="font-medium text-ink">
            {source.citation?.record_title || source.record_type}
          </div>
          <div className="mt-1">
            {source.snippet || source.text}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState(null);

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
    <div className="flex flex-col h-[calc(100vh-8rem)]">
      <h1 className="font-display text-2xl font-semibold mb-1">Chat</h1>
      <p className="text-slate text-sm mb-6">
        Ask questions about the documents in your sidebar.
      </p>

      <div className="flex-1 border border-line rounded-md bg-white/40 p-4 overflow-y-auto space-y-3">
        {!messages.length && (
          <p className="text-sm text-slate italic">
            No messages yet. Ask something about an uploaded document to get started.
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
            <div>{m.text}</div>
            {m.role === "assistant" && <SourceList sources={m.sources} />}
          </div>
        ))}
      </div>

      {error && <p className="text-xs text-ochre-600 mt-2">{error}</p>}

      <div className="flex gap-2 mt-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about a participant's documents…"
          className="flex-1 border border-line rounded-md px-3 py-2.5 text-sm focus:border-teal-500 outline-none"
        />
        <button
          onClick={send}
          disabled={sending}
          className="px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 disabled:opacity-50 transition-colors"
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </div>
    </div>
  );
}
