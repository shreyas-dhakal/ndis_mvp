import { useEffect, useState } from "react";
import { api } from "../lib/api.js";
import DeadlineChip from "../components/DeadlineChip.jsx";

function TaskList({ view, showApproveDismiss }) {
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
        <div key={task.id} className="border border-line rounded-md p-4 bg-white/40">
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="font-display font-semibold text-sm capitalize">
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
  const [tab, setTab] = useState("pending");

  return (
    <div>
      <h1 className="font-display text-2xl font-semibold mb-1">Tasks</h1>
      <p className="text-slate text-sm mb-6">
        Reportable-incident checks surfaced by the trigger agent.
      </p>

      <div className="flex gap-1 mb-5 w-fit border border-line rounded-sm p-0.5">
        {[
          ["pending", "Needs Review"],
          ["confirmed", "Confirmed — Pending Action"],
        ].map(([value, label]) => (
          <button
            key={value}
            onClick={() => setTab(value)}
            className={`px-4 py-1.5 text-sm rounded-sm font-medium transition-colors ${
              tab === value ? "bg-teal-500 text-white" : "text-slate hover:text-ink"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "pending" ? (
        <TaskList view="pending" showApproveDismiss />
      ) : (
        <TaskList view="confirmed" showApproveDismiss={false} />
      )}
    </div>
  );
}
