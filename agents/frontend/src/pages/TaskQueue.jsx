import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../lib/api.js";
import DeadlineChip from "../components/DeadlineChip.jsx";

function TaskList({ view, showApproveDismiss, highlightId }) {
  const [tasks, setTasks] = useState([]);
  const [error, setError] = useState(null);
  const [dismissingId, setDismissingId] = useState(null);
  const [reason, setReason] = useState("");

  const load = async () => {
    try {
      const data = await api.get("/tasks", { view });
      setTasks(data.tasks || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 30000); // keep countdown rings current
    return () => clearInterval(interval);
  }, [view]);

  const approve = async (id) => {
    await api.post(`/tasks/${id}/approve`, { reviewer: "web_user" });
    load();
  };

  const dismiss = async (id) => {
    await api.post(`/tasks/${id}/dismiss`, { reviewer: "web_user", reason });
    setDismissingId(null);
    setReason("");
    load();
  };

  const action = async (id) => {
    await api.post(`/tasks/${id}/action`, { reviewer: "web_user" });
    load();
  };

  if (error) {
    return <p className="text-sm text-ochre-600">{error}</p>;
  }

  if (!tasks.length) {
    return <p className="text-sm text-slate italic">Nothing here.</p>;
  }

  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <div
          key={task.id}
          id={`task-${task.id}`}
          className={`surface p-5 ${
            highlightId === task.id ? "border-teal-500 ring-2 ring-teal-500/30" : ""
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="mb-1 flex items-center gap-2 font-display font-semibold text-sm capitalize">
                <span className="h-2 w-2 rounded-full bg-ochre-400" />
                {task.trigger_id.replace(/_/g, " ")}
              </div>
              <div className="text-xs text-slate font-mono mt-0.5">
                From note logged{" "}
                {new Date(task.created_at).toLocaleString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </div>
            </div>
            <DeadlineChip createdAt={task.created_at} deadline={task.deadline} />
          </div>

          <p className="text-sm mt-3">
            Matched on: <span className="italic text-slate">{task.reasoning}</span>
          </p>

          <div className="mt-3 flex gap-2 items-start">
            {showApproveDismiss ? (
              <>
                <button
                  onClick={() => approve(task.id)}
                  className="px-4 py-1.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors"
                >
                  Approve
                </button>
                <button
                  onClick={() => setDismissingId(task.id)}
                  className="px-4 py-1.5 border border-line text-sm font-medium rounded-md hover:bg-paper transition-colors"
                >
                  Dismiss
                </button>
                {dismissingId === task.id && (
                  <div className="flex gap-2 flex-1">
                    <input
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Why dismiss this?"
                      className="flex-1 border border-line rounded-md px-3 py-1.5 text-sm focus:border-teal-500 outline-none"
                    />
                    <button
                      onClick={() => dismiss(task.id)}
                      className="px-3 py-1.5 text-sm font-medium text-red-600 hover:bg-red-50 rounded-md transition-colors"
                    >
                      Confirm dismiss
                    </button>
                  </div>
                )}
              </>
            ) : (
              <button
                onClick={() => action(task.id)}
                className="px-4 py-1.5 bg-teal-500 text-white text-sm font-medium rounded-md hover:bg-teal-600 transition-colors"
              >
                Mark as actioned
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function TaskQueue() {
  const [searchParams] = useSearchParams();
  const initialView = searchParams.get("view");
  const highlightId = searchParams.get("highlight");
  const [tab, setTab] = useState(initialView === "confirmed" ? "confirmed" : "pending");
  const [pendingCount, setPendingCount] = useState(null);

  useEffect(() => {
    if (!highlightId) return;
    const el = document.getElementById(`task-${highlightId}`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [tab, highlightId]);

  useEffect(() => {
    let active = true;
    const loadPendingCount = async () => {
      try {
        const data = await api.get("/tasks", { view: "pending" });
        if (active) setPendingCount((data.tasks || []).length);
      } catch {
        if (active) setPendingCount(null);
      }
    };

    loadPendingCount();
    const interval = setInterval(loadPendingCount, 30000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const attentionLabel = pendingCount === 1 ? "task needing attention" : "tasks needing attention";

  return (
    <div className="space-y-8">
      <section><div className="eyebrow mb-4">Your to-do list</div><h1 className="display-title max-w-[700px]">A clear next step<br /><span className="text-teal-600">when it matters.</span></h1><p className="mt-5 max-w-[560px] text-[15px] leading-7 text-slate">Important follow-ups from your notes, brought together so nothing gets missed.</p></section>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="surface p-5"><div className="font-display text-3xl font-semibold tracking-tight">24h</div><div className="mt-1 text-xs text-slate">fastest response window</div></div>
        <div className="surface p-5"><div className="font-display text-3xl font-semibold tracking-tight">100%</div><div className="mt-1 text-xs text-slate">reviewable decisions</div></div>
        <button onClick={() => setTab("pending")} className="surface p-5 text-left transition-colors hover:border-teal-400 hover:bg-teal-50/40">
          <div className="flex items-start justify-between gap-3">
            <div className="font-display text-3xl font-semibold tracking-tight">{pendingCount === null ? "--" : pendingCount}</div>
            <span className="text-lg text-teal-700" aria-hidden="true">↗</span>
          </div>
          <div className="mt-1 text-xs text-slate">{pendingCount === null ? "checking queue" : attentionLabel}</div>
        </button>
      </div>

      <div className="flex gap-1 mb-5 w-fit rounded-lg border border-line bg-white p-1">
        {[
           ["pending", "Needs your review"],
           ["confirmed", "Ready to action"],
        ].map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`px-4 py-1.5 text-sm rounded-sm font-medium transition-colors ${
              tab === value ? "bg-ink text-white" : "text-slate hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "pending" ? (
        <TaskList view="pending" showApproveDismiss highlightId={highlightId} />
      ) : (
        <TaskList view="confirmed" showApproveDismiss={false} highlightId={highlightId} />
      )}
    </div>
  );
}
