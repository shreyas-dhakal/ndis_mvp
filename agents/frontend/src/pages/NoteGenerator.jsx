import { useEffect, useRef, useState } from "react";
import { api, BASE_URL } from "../lib/api.js";

const FIELDS = [
  ["subjective", "Subjective"], ["objective", "Objective"], ["assessment", "Assessment"],
  ["plan", "Plan"], ["participant_voice", "Participant voice"], ["support_type", "Support type"],
  ["risks_incidents", "Risks / incidents"],
];

const formatDuration = (seconds) => {
  const mins = Math.floor(seconds / 60).toString().padStart(2, "0");
  const secs = (seconds % 60).toString().padStart(2, "0");
  return `${mins}:${secs}`;
};

const getSupportedMimeType = () => {
  if (typeof MediaRecorder === "undefined") return "";
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
  return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
};

const fileExtensionForMimeType = (mimeType) => {
  if (mimeType.includes("ogg")) return "ogg";
  if (mimeType.includes("mp4")) return "mp4";
  return "webm";
};

export default function NoteGenerator() {
  const [status, setStatus] = useState("idle");
  const [whisperSize, setWhisperSize] = useState("small");
  const [threadId, setThreadId] = useState(null);
  const [note, setNote] = useState(null);
  const [pdfPath, setPdfPath] = useState(null);
  const [a2, setA2] = useState({ created: false, triggerId: null });
  const [feedback, setFeedback] = useState("");
  const [error, setError] = useState(null);
  const [recorderState, setRecorderState] = useState("idle");
  const [recordedAudio, setRecordedAudio] = useState(null);
  const [recordingSeconds, setRecordingSeconds] = useState(0);

  const mediaRecorderRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const discardRecordingRef = useRef(false);

  const clearTimer = () => {
    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const stopMediaTracks = () => {
    mediaStreamRef.current?.getTracks().forEach((track) => track.stop());
    mediaStreamRef.current = null;
  };

  const releaseRecordedAudio = () => {
    setRecordedAudio((current) => {
      if (current?.url) URL.revokeObjectURL(current.url);
      return null;
    });
  };

  useEffect(() => () => {
    clearTimer();
    discardRecordingRef.current = true;
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
    stopMediaTracks();
  }, []);

  useEffect(() => () => {
    if (recordedAudio?.url) URL.revokeObjectURL(recordedAudio.url);
  }, [recordedAudio]);

  const run = async (request) => {
    setStatus("loading"); setError(null);
    try {
      const data = await request();
      setThreadId(data.thread_id ?? threadId); setStatus(data.status); setNote(data.note ?? null); setPdfPath(data.pdf_path ?? null);
      setA2({ created: data.a2_task_created ?? false, triggerId: data.a2_trigger_id ?? null });
    } catch (err) { setError(err.message); setStatus("idle"); }
  };

  const startRecording = async () => {
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("This browser does not support in-app audio recording.");
      return;
    }

    setError(null);
    setRecorderState("requesting");

    try {
      discardRecordingRef.current = false;
      releaseRecordedAudio();
      chunksRef.current = [];
      setRecordingSeconds(0);

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaStreamRef.current = stream;

      const mimeType = getSupportedMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data?.size) chunksRef.current.push(event.data);
      };

      recorder.onstop = () => {
        clearTimer();
        stopMediaTracks();
        mediaRecorderRef.current = null;

        if (discardRecordingRef.current) {
          chunksRef.current = [];
          discardRecordingRef.current = false;
          return;
        }

        const blobType = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: blobType });
        const url = URL.createObjectURL(blob);

        setRecordedAudio({
          blob,
          url,
          mimeType: blobType,
          name: `conversation-${Date.now()}.${fileExtensionForMimeType(blobType)}`,
        });
        setRecorderState("recorded");
      };

      recorder.onerror = () => {
        clearTimer();
        stopMediaTracks();
        mediaRecorderRef.current = null;
        setRecorderState("idle");
        setError("Recording failed. Please try again.");
      };

      recorder.start();
      setRecorderState("recording");
      timerRef.current = window.setInterval(() => {
        setRecordingSeconds((current) => current + 1);
      }, 1000);
    } catch (err) {
      clearTimer();
      stopMediaTracks();
      setRecorderState("idle");
      setError(err?.name === "NotAllowedError" ? "Microphone access was blocked. Please allow access and try again." : "Could not start recording. Check your microphone and try again.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current?.state === "recording") {
      mediaRecorderRef.current.stop();
      setRecorderState("processing");
    }
  };

  const generateAudio = () => {
    if (!recordedAudio?.blob) return setError("Record a conversation before generating a note.");
    const form = new FormData();
    form.append("file", new File([recordedAudio.blob], recordedAudio.name, { type: recordedAudio.mimeType }));
    form.append("whisper_model_size", whisperSize);
    run(() => api.postForm("/generate/audio", form));
  };

  const resume = (feedbackValue) => run(() => api.post("/generate/resume", { thread_id: threadId, feedback: feedbackValue }));

  const reset = () => {
    clearTimer();
    discardRecordingRef.current = true;
    if (mediaRecorderRef.current?.state === "recording") mediaRecorderRef.current.stop();
    stopMediaTracks();
    setStatus("idle");
    setThreadId(null);
    setNote(null);
    setPdfPath(null);
    setA2({ created: false, triggerId: null });
    setFeedback("");
    setError(null);
    setRecorderState("idle");
    setRecordingSeconds(0);
    releaseRecordedAudio();
  };

  const documentedSections = note
    ? FIELDS.reduce((count, [key]) => count + (note[key] ? 1 : 0), 0) + (note.consent_noted !== null && note.consent_noted !== undefined ? 1 : 0)
    : 0;

  let summaryEyebrow = "Workflow status";
  let summaryTitle = "Start a recorded session";
  let summaryDetail = "Record the conversation between the participant and support worker, then send it to Caseload AI.";
  let summaryAction = null;

  if (status === "loading") {
    summaryTitle = "Generating your draft";
    summaryDetail = "Caseload AI is extracting goals, outcomes, risks, and participant voice now.";
    summaryAction = <button disabled className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white opacity-70">Working…</button>;
  } else if (status === "awaiting_review" && note) {
    summaryEyebrow = "Ready for review";
    summaryTitle = "Draft assembled";
    summaryDetail = `${documentedSections} sections captured${note.linked_goals?.length ? ` · ${note.linked_goals.length} linked goals` : ""}`;
    summaryAction = <button onClick={() => resume("yes")} className="lime-button px-4 py-2 text-sm">Approve draft</button>;
  } else if (status === "done") {
    summaryEyebrow = "Complete";
    summaryTitle = "PDF ready";
    summaryDetail = a2.created
      ? `Progress note approved · ${a2.triggerId?.replace(/_/g, " ") || "follow-up task created"}`
      : "Progress note approved and ready to download.";
    summaryAction = pdfPath
      ? <a href={`${BASE_URL}/download/pdf?path=${encodeURIComponent(pdfPath)}`} className="lime-button px-4 py-2 text-sm" download>Download PDF</a>
      : <button onClick={reset} className="rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink">Start another</button>;
  } else if (recorderState === "recording") {
    summaryEyebrow = "Recording live";
    summaryTitle = "Conversation in progress";
    summaryDetail = `${formatDuration(recordingSeconds)} captured so far.`;
    summaryAction = <button onClick={stopRecording} className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white">Stop recording</button>;
  } else if (recorderState === "processing") {
    summaryEyebrow = "Preparing audio";
    summaryTitle = "Finalising recording";
    summaryDetail = "Packaging the conversation so it can be transcribed and reviewed.";
    summaryAction = <button disabled className="rounded-lg bg-ink px-4 py-2 text-sm font-medium text-white opacity-70">Please wait</button>;
  } else if (recordedAudio) {
    summaryTitle = "Recording ready";
    summaryDetail = `${recordedAudio.name} is queued for transcription with the ${whisperSize} model.`;
    summaryAction = <button onClick={generateAudio} className="lime-button px-4 py-2 text-sm">Transcribe &amp; generate</button>;
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div><div className="eyebrow mb-2">New progress note</div><h1 className="display-title max-w-[680px] text-[2.5rem] md:text-[3.2rem]">Good care deserves <span className="text-teal-600">a better record.</span></h1><p className="mt-4 max-w-[560px] text-[15px] leading-7 text-slate">Every plan. Every call. Every detail. <span className="font-medium text-ink">One clear record, one conversation away.</span></p></div>
        <div className="surface shrink-0 px-4 py-3 md:max-w-sm">
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <span className="status-dot mt-1" />
              <div>
                <div className="font-mono text-[10px] uppercase tracking-widest text-slate">{summaryEyebrow}</div>
                <div className="text-sm font-semibold">{summaryTitle}</div>
                <div className="mt-1 text-xs leading-5 text-slate">{summaryDetail}</div>
                {threadId && <div className="mt-2 font-mono text-[10px] uppercase tracking-widest text-slate">Session {threadId.slice(0, 8)}</div>}
              </div>
            </div>
            {summaryAction}
          </div>
        </div>
      </section>

      {error && <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      {status === "idle" && <div className="surface overflow-hidden p-5 md:p-8">
        <div className="mb-5 flex items-start justify-between gap-4"><div><div className="eyebrow mb-2">Step 1 of 2</div><h2 className="font-display text-2xl font-semibold tracking-tight">Record the support conversation</h2></div><span className="hidden rounded-full bg-teal-50 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-teal-700 sm:block">Ready when you are</span></div>
        <div className="rounded-2xl border border-line bg-paper p-5">
          <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
            <div className="max-w-xl">
              <div className="text-sm font-semibold text-ink">Start recording from the browser</div>
              <p className="mt-2 text-sm leading-6 text-slate">Use this during the participant and support worker conversation. When you stop the recording, Caseload AI will transcribe it and pass it into the note and incident-check agents.</p>
              <p className="mt-3 text-xs leading-5 text-slate">Make sure the participant knows the session is being recorded and that the microphone can clearly hear both voices.</p>
            </div>
            <div className="rounded-2xl bg-teal-50 px-4 py-3 text-center md:min-w-[170px]">
              <div className="font-mono text-[10px] uppercase tracking-[0.25em] text-teal-700">Capture</div>
              <div className="mt-2 font-display text-3xl font-semibold text-ink">{formatDuration(recordingSeconds)}</div>
              <div className="mt-1 text-xs text-slate">{recorderState === "recording" ? "Recording live" : recordedAudio ? "Ready to process" : "Waiting to start"}</div>
            </div>
          </div>

          <div className="mt-5 flex flex-wrap items-center gap-3">
            {recorderState === "recording"
              ? <button onClick={stopRecording} className="rounded-lg bg-ink px-5 py-3 text-sm font-medium text-white">Stop recording</button>
              : <button onClick={startRecording} disabled={recorderState === "requesting" || recorderState === "processing" || status === "loading"} className="lime-button px-5 py-3 text-sm disabled:cursor-not-allowed disabled:opacity-60">{recorderState === "requesting" ? "Allow microphone…" : recordedAudio ? "Record again" : "Start recording"}</button>}
            {recordedAudio && <button onClick={generateAudio} className="rounded-lg border border-teal-500 px-5 py-3 text-sm font-medium text-teal-700">Transcribe &amp; generate note</button>}
          </div>

          <div className="mt-5 flex flex-wrap items-end justify-between gap-4 border-t border-line pt-5">
            <label className="text-xs font-semibold uppercase tracking-wide text-slate">Transcription quality<select value={whisperSize} onChange={(e) => setWhisperSize(e.target.value)} className="mt-1 block rounded-lg border border-line bg-paper p-2 text-sm font-normal normal-case"><option value="small">Fast · small</option><option value="medium">Balanced · medium</option><option value="large-v3">Highest · large-v3</option></select></label>
            <span className="text-xs text-slate">Workflow: record conversation -&gt; transcribe audio -&gt; generate draft -&gt; human review -&gt; run follow-up agents</span>
          </div>

          {recordedAudio && <div className="mt-5 rounded-2xl border border-line bg-white p-4"><div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate">Recorded conversation</div><audio controls src={recordedAudio.url} className="w-full" /><div className="mt-2 text-xs text-slate">{recordedAudio.name}</div></div>}
        </div>
      </div>}
      {status === "loading" && <div className="surface flex min-h-[300px] flex-col items-center justify-center p-10 text-center"><div className="mb-5 h-12 w-12 animate-pulse rounded-2xl bg-lime-200" /><div className="font-display text-xl font-semibold">Making the record legible…</div><p className="mt-2 max-w-sm text-sm leading-6 text-slate">Caseload AI is listening for goals, outcomes, risks, and the participant's own voice.</p></div>}
      {status === "awaiting_review" && note && <div className="surface p-5 md:p-8"><div className="mb-7 flex items-center justify-between"><div><div className="eyebrow mb-2">Draft ready</div><h2 className="font-display text-2xl font-semibold">Review the signal</h2></div><span className="rounded-full bg-ochre-50 px-3 py-1 font-mono text-[10px] uppercase tracking-wider text-ochre-600">Human review required</span></div><div className="grid gap-4 md:grid-cols-2">{FIELDS.map(([key, label]) => <div key={key}><div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate">{label}</div><div className="min-h-[3rem] rounded-xl bg-teal-50 p-3 text-sm leading-6">{note[key] || <span className="italic text-slate">Not documented</span>}</div></div>)}<div><div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate">Consent noted</div><div className="rounded-xl bg-teal-50 p-3 text-sm">{note.consent_noted === true ? "Yes" : note.consent_noted === false ? "No" : "Not documented"}</div></div></div><div className="mt-5"><div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate">Linked goals</div><div className="text-sm">{note.linked_goals?.length ? note.linked_goals.join(", ") : "None linked"}</div></div><hr className="my-6 border-line" /><div className="flex flex-col gap-3 md:flex-row md:items-start"><button onClick={() => resume("yes")} className="lime-button shrink-0 px-5 py-3 text-sm">Approve &amp; generate PDF</button><div className="flex flex-1 gap-2"><input value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="Describe a change to the draft…" className="min-w-0 flex-1 rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-teal-500" /><button onClick={() => feedback.trim() ? resume(feedback) : setError("Please describe the changes, or use Approve.")} className="rounded-lg border border-teal-500 px-4 py-2 text-sm font-medium text-teal-700">Submit</button></div></div></div>}
      {status === "done" && <div className="surface p-6 md:p-8"><div className="mb-5 rounded-xl bg-teal-50 px-4 py-3 text-sm font-medium text-teal-700">NDIS progress note approved and ready.</div>{a2.created && <div className="mb-5 rounded-xl bg-ochre-50 px-4 py-3 text-sm text-ochre-600">This note triggered a reportable-incident check: <strong className="font-mono">{a2.triggerId?.replace(/_/g, " ")}</strong>. A task has been created.</div>}{pdfPath ? <a href={`${BASE_URL}/download/pdf?path=${encodeURIComponent(pdfPath)}`} className="lime-button inline-block px-5 py-3 text-sm" download>Download PDF progress note ↗</a> : <p className="text-sm text-ochre-600">No PDF path was returned by the backend.</p>}<div className="mt-5"><button onClick={reset} className="text-sm text-slate underline underline-offset-2">Start a new note</button></div></div>}
    </div>
  );
}
