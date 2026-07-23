import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Tooltip,
  Legend,
} from "chart.js";
import { Bar, Line } from "react-chartjs-2";
import { useDashboardStats } from "../hooks/useDashboardStats.js";
import { useEntities } from "../hooks/useEntities.js";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  Tooltip,
  Legend
);

const TEAL = "#2F6F6B";
const OCHRE = "#B8863B";
const LINE = "#DCD8CE";
const SLATE = "#5B6B6A";

const CHART_FONT = { family: "'DM Mono', monospace", size: 10 };

function KpiCard({ value, label, tone = "ink" }) {
  const toneClass = tone === "ochre" ? "text-ochre-600" : tone === "teal" ? "text-teal-600" : "text-ink";
  return (
    <div className="surface p-5">
      <div className={`font-display text-3xl font-semibold tracking-tight ${toneClass}`}>{value}</div>
      <div className="mt-1 text-xs text-slate">{label}</div>
    </div>
  );
}

function statusToView(status) {
  return status === "draft" ? "pending" : "confirmed";
}

export default function Dashboard() {
  const [entityId, setEntityId] = useState("");
  const [window_, setWindow] = useState("30d");
  const { entities } = useEntities();
  const { stats, error } = useDashboardStats(entityId || undefined);

  const categoryData = useMemo(() => {
    const rows = stats?.incidents_by_category?.[window_] || [];
    return {
      labels: rows.map((row) => (row.category || "uncategorised").replace(/_/g, " ")),
      datasets: [
        {
          label: "Incidents",
          data: rows.map((row) => row.count),
          backgroundColor: TEAL,
          borderRadius: 6,
          maxBarThickness: 40,
        },
      ],
    };
  }, [stats, window_]);

  const trendData = useMemo(() => {
    const rows = stats?.notes_trend || [];
    return {
      labels: rows.map((row) =>
        new Date(row.week_start).toLocaleDateString(undefined, { month: "short", day: "numeric" })
      ),
      datasets: [
        {
          label: "Notes completed",
          data: rows.map((row) => row.count),
          borderColor: OCHRE,
          backgroundColor: "rgba(184,134,59,0.15)",
          tension: 0.35,
          fill: true,
          pointRadius: 3,
          pointBackgroundColor: OCHRE,
        },
      ],
    };
  }, [stats]);

  const barOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { font: CHART_FONT, color: SLATE }, grid: { display: false } },
      y: { ticks: { font: CHART_FONT, color: SLATE, precision: 0 }, grid: { color: LINE } },
    },
  };

  const lineOptions = {
    responsive: true,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { font: CHART_FONT, color: SLATE }, grid: { display: false } },
      y: { ticks: { font: CHART_FONT, color: SLATE, precision: 0 }, grid: { color: LINE } },
    },
  };

  const monthDelta = stats ? stats.incidents_this_month - stats.incidents_last_month : 0;
  const monthDeltaLabel =
    stats && stats.incidents_last_month > 0
      ? `${monthDelta >= 0 ? "+" : ""}${monthDelta} vs last month`
      : "vs last month";

  return (
    <div className="space-y-8">
      <section className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
        <div>
          <div className="eyebrow mb-4">Org overview</div>
          <h1 className="display-title max-w-[700px]">
            Everything worth knowing,
            <br />
            <span className="text-teal-600">at a glance.</span>
          </h1>
          <p className="mt-5 max-w-[560px] text-[15px] leading-7 text-slate">
            A snapshot of open work, flagged incidents, and documentation across{" "}
            {entityId ? "this participant." : "the org."}
          </p>
        </div>
        <label className="shrink-0 text-xs font-semibold uppercase tracking-wide text-slate">
          Participant
          <select
            value={entityId}
            onChange={(e) => setEntityId(e.target.value)}
            className="mt-1 block w-full min-w-[220px] rounded-lg border border-line bg-paper p-2 text-sm font-normal normal-case"
          >
            <option value="">All participants</option>
            {entities.map((entity) => (
              <option key={entity.id} value={entity.id}>
                {entity.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard value={stats ? stats.open_tasks : "--"} label="open tasks" />
        <KpiCard
          value={stats ? stats.incidents_this_month : "--"}
          label={`incidents this month · ${monthDeltaLabel}`}
          tone="ochre"
        />
        <KpiCard
          value={stats ? stats.tasks_pending_this_week : "--"}
          label="tasks pending review this week"
          tone="ochre"
        />
        <KpiCard
          value={stats ? stats.documents_ingested_this_week : "--"}
          label="documents ingested this week"
          tone="teal"
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="surface p-5 md:p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <div className="eyebrow mb-1">Risk & escalation</div>
              <h2 className="font-display text-lg font-semibold">Incidents by category</h2>
            </div>
            <div className="flex gap-1 w-fit rounded-lg border border-line bg-white p-1">
              {[
                ["30d", "30 days"],
                ["90d", "90 days"],
              ].map(([value, label]) => (
                <button
                  key={value}
                  onClick={() => setWindow(value)}
                  className={`px-3 py-1 text-xs rounded-sm font-medium transition-colors ${
                    window_ === value ? "bg-ink text-white" : "text-slate hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {stats && categoryData.labels.length ? (
            <Bar data={categoryData} options={barOptions} />
          ) : (
            <p className="text-sm text-slate italic">
              {stats ? "No flagged incidents in this window." : "Loading…"}
            </p>
          )}
        </div>

        <div className="surface p-5 md:p-6">
          <div className="mb-4">
            <div className="eyebrow mb-1">Documentation</div>
            <h2 className="font-display text-lg font-semibold">Notes completed · last 4 weeks</h2>
          </div>
          {stats ? <Line data={trendData} options={lineOptions} /> : <p className="text-sm text-slate italic">Loading…</p>}
        </div>
      </div>

      <div className="surface p-5 md:p-6">
        <div className="mb-4">
          <div className="eyebrow mb-1">Needs attention</div>
          <h2 className="font-display text-lg font-semibold">Recent flagged tasks</h2>
        </div>
        {!stats ? (
          <p className="text-sm text-slate italic">Loading…</p>
        ) : stats.recent_flagged_tasks.length === 0 ? (
          <p className="text-sm text-slate italic">Nothing flagged yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line text-left font-mono text-[10px] uppercase tracking-wider text-slate">
                  <th className="pb-2 pr-4">Participant</th>
                  <th className="pb-2 pr-4">Category</th>
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2" />
                </tr>
              </thead>
              <tbody>
                {stats.recent_flagged_tasks.map((task) => (
                  <tr key={task.id} className="border-b border-line/60 last:border-0">
                    <td className="py-2.5 pr-4 font-medium">{task.participant}</td>
                    <td className="py-2.5 pr-4 capitalize text-slate">
                      {(task.category || "uncategorised").replace(/_/g, " ")}
                    </td>
                    <td className="py-2.5 pr-4 font-mono text-xs text-slate">
                      {new Date(task.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                      })}
                    </td>
                    <td className="py-2.5 pr-4">
                      <span
                        className={`rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
                          task.status === "draft"
                            ? "bg-ochre-50 text-ochre-600"
                            : "bg-teal-50 text-teal-700"
                        }`}
                      >
                        {task.status === "draft" ? "pending" : task.status}
                      </span>
                    </td>
                    <td className="py-2.5 text-right">
                      <Link
                        to={`/tasks?view=${statusToView(task.status)}&highlight=${task.id}`}
                        className="text-xs font-medium text-teal-700 hover:underline"
                      >
                        Review ↗
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
