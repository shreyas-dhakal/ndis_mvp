import { useState } from "react";
import { api, BASE_URL } from "../lib/api.js";

const FIELD_LABELS = [
  ["subjective", "Subjective"],
  ["objective", "Objective"],
  ["assessment", "Assessment"],
  ["plan", "Plan"],
  ["participant_voice", "Participant Voice"],
  ["support_type", "Support Type"],
  ["risks_incidents", "Risks / Incidents"],
];

export default function NoteGenerator() {
  const [status, setStatus] = useState("idle"); // idle | loading | awaiting_review | done
  const [mode, setMode] = useState("text");
  const [transcript, setTranscript] = useState("");
  const [audioFile, setAudioFile] = useState(null);
  const [whisperSize, setWhisperSize] = useState("small");
  const [threadId, setThreadId] = useState(null);
  const [note, setNote] = useState(null);
  const [pdfPath, setPdfPath] = useState(null);
  const [a2, setA2] = useState({ created: false, triggerId: null });
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState(null);

  const applyResponse = (data) => {
    setThreadId(data.thread_id ?? threadId);
    setStatus(data.status);
    setNote(data.note ?? null);
    setPdfPath(data.pdf_path ?? null);
    setA2({
      created: data.a2_task_created ?? false,
      triggerId: data.a2_trigger_id ?? null,
    });
    setError(null);
  };

  const runGuarded = async (fn) => {
    setStatus("loading");
    try {
      const data = await fn();
      applyResponse(data);
    } catch (err) {
      setError(err.message);
      setStatus("idle");
    }
  };

  const handleGenerateFromText = () => {
    if (!transcript.trim()) {
      setError("Please enter a transcript");
      return;
    }
    runGuarded(() => api.post("/generate/text", { transcript }));
  };

  const handleGenerateFromAudio = () => {
    if (!audioFile) {
      setError("Please upload an audio file");
      return;
    }
    const formData = new FormData();
    formData.append("file", audioFile);
    formData.append("whisper_model_size", whisperSize);
    runGuarded(() => api.postForm("/generate/audio", formData));
  };

  const handleResume = (feedbackValue) => {
    runGuarded(() =>
      api.post("/generate/resume", { thread_id: threadId, feedback: feedbackValue })
    );
  };

  const handleReset = () => {
    setStatus("idle");
    setTranscript("");
    setAudioFile(null);
    setThreadId(null);
    setNote(null);
    setPdfPath(null);
    setA2({ created: false, triggerId: null });
    setFeedback("");
    setError(null);
  };

  return (
    <div>
      <h1 className="font-display text-2xl font-semibold mb-1">
        Note Generator
      </h1>
      <p className="text-slate text-sm mb-6">
        Turn a transcript or recording into a structured NDIS progress note.
      </p>

      {error && (
        <div className="mb-4 px-4 py-3 rounded-md bg-red-50 text-red-700 text-sm">
          {error}
        </div>
      )}

      {status === "idle" && (
        <div className="border border-line rounded-md p-6 bg-white/40">
          <div className="flex gap-1 mb-5 w-fit border border-line rounded-sm p-0.5">
            {["text", "audio"].map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={`px-4 py-1.5 text-sm rounded-sm font-medium capitalize transition-colors ${
                  mode === m
                    ? "bg-teal-500 text-white"
                    : "text-slate hover:text-ink"
                }`}
              >
                {m === "text" ? "Text Transcript" : "Upload Audio"}
              </button>
            ))}
          </div>

          {mode === "text" ? (
            <>
              <textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                placeholder="Paste conversation transcript here"
                rows={10}
                className="w-full border border-line rounded-md p-3 text-sm font-mono focus:border-teal-500 outline-none resize-y"
              />
              <button
                onClick={handleGenerateFromText}
                className="mt-4 px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors"
              >
                Generate Progress Note
              </button>
            </>
          ) : (
            <>
              <input
                type="file"
                accept=".mp3,.wav,.m4a,.ogg"
                onChange={(e) => setAudioFile(e.target.files?.[0] ?? null)}
                className="block w-full text-sm border border-line rounded-md p-3"
              />
              <label className="block mt-4 text-sm font-medium text-slate">
                Whisper model size
                <select
                  value={whisperSize}
                  onChange={(e) => setWhisperSize(e.target.value)}
                  className="block mt-1 border border-line rounded-md p-2 text-sm"
                >
                  <option value="small">small</option>
                  <option value="medium">medium</option>
                  <option value="large-v3">large-v3</option>
                </select>
              </label>
              <button
                onClick={handleGenerateFromAudio}
                className="mt-4 px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors"
              >
                Transcribe &amp; Generate Note
              </button>
            </>
          )}
        </div>
      )}

      {status === "loading" && (
        <div className="border border-line rounded-md p-10 text-center text-slate text-sm">
          Working on it…
        </div>
      )}

      {status === "awaiting_review" && note && (
        <div className="border border-line rounded-md p-6 bg-white/40">
          <h2 className="font-display text-lg font-semibold mb-4">
            Review Progress Note
          </h2>

          <div className="grid md:grid-cols-2 gap-4">
            {FIELD_LABELS.map(([key, label]) => (
              <div key={key}>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate mb-1">
                  {label}
                </div>
                <div className="text-sm bg-teal-50 rounded-sm p-3 min-h-[3rem]">
                  {note[key] || <span className="italic text-slate">Not documented</span>}
                </div>
              </div>
            ))}
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-slate mb-1">
                Consent Noted
              </div>
              <div className="text-sm bg-teal-50 rounded-sm p-3">
                {note.consent_noted === true
                  ? "Yes"
                  : note.consent_noted === false
                  ? "No"
                  : "Not documented"}
              </div>
            </div>
          </div>

          <div className="mt-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate mb-1">
              Linked Goals
            </div>
            <div className="text-sm">
              {note.linked_goals?.length ? note.linked_goals.join(", ") : "None linked"}
            </div>
          </div>

          <hr className="my-5 border-line" />

          <div className="flex flex-col md:flex-row gap-3 md:items-start">
            <button
              onClick={() => handleResume("yes")}
              className="px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors shrink-0"
            >
              Approve &amp; Generate PDF
            </button>
            <div className="flex-1 flex gap-2">
              <input
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Or describe changes you'd like, e.g. add more detail to the plan"
                className="flex-1 border border-line rounded-md px-3 py-2 text-sm focus:border-teal-500 outline-none"
              />
              <button
                onClick={() => {
                  if (!feedback.trim()) {
                    setError("Please describe the changes, or use Approve.");
                    return;
                  }
                  handleResume(feedback);
                }}
                className="px-4 py-2 border border-teal-500 text-teal-700 text-sm font-medium rounded-md hover:bg-teal-50 transition-colors"
              >
                Submit Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {status === "done" && (
        <div className="border border-line rounded-md p-6 bg-white/40">
          <div className="px-4 py-3 rounded-md bg-teal-50 text-teal-700 text-sm font-medium mb-4">
            NDIS Progress Note approved
          </div>

          {a2.created && (
            <div className="px-4 py-3 rounded-md bg-ochre-50 text-ochre-600 text-sm mb-4">
              This note triggered a reportable-incident check:{" "}
              <strong className="font-mono">
                {a2.triggerId?.replace(/_/g, " ")}
              </strong>
              . A task has been created — see the Tasks tab.
            </div>
          )}

          {pdfPath ? (
            <a
              href={`${BASE_URL}/download/pdf?path=${encodeURIComponent(pdfPath)}`}
              className="inline-block px-5 py-2.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors"
              download
            >
              Download PDF Progress Note
            </a>
          ) : (
            <p className="text-sm text-ochre-600">No PDF path was returned by the backend.</p>
          )}

          <div className="mt-5">
            <button
              onClick={handleReset}
              className="text-sm text-slate hover:text-ink underline underline-offset-2"
            >
              Start new note
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
