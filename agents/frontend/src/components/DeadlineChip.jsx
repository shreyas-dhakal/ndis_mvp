// The countdown always runs from the note's timestamp, not from when a
// human approves the task — NDIS reporting windows start at the incident,
// so this component is given createdAt + deadline directly rather than
// computing its own "time since approval".
const RADIUS = 9;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function getUrgency(hoursLeft) {
  if (hoursLeft < 0) return { label: "OVERDUE", tone: "red" };
  if (hoursLeft < 4) return { label: `${hoursLeft.toFixed(1)}h left`, tone: "red" };
  if (hoursLeft < 24) return { label: `${hoursLeft.toFixed(1)}h left`, tone: "amber" };
  return { label: `${(hoursLeft / 24).toFixed(1)}d left`, tone: "green" };
}

const TONE_STYLES = {
  red: { ring: "#C1443B", bg: "bg-red-50", text: "text-red-700" },
  amber: { ring: "#C9963F", bg: "bg-ochre-50", text: "text-ochre-600" },
  green: { ring: "#3F7A5A", bg: "bg-teal-50", text: "text-teal-700" },
};

export default function DeadlineChip({ createdAt, deadline }) {
  const created = new Date(createdAt).getTime();
  const due = new Date(deadline).getTime();
  const now = Date.now();

  const totalWindow = due - created;
  const remaining = due - now;
  const hoursLeft = remaining / (1000 * 60 * 60);

  const elapsedFraction = totalWindow > 0
    ? Math.min(1, Math.max(0, (now - created) / totalWindow))
    : 1;

  const { label, tone } = getUrgency(hoursLeft);
  const style = TONE_STYLES[tone];
  const dashOffset = CIRCUMFERENCE * (1 - elapsedFraction);
  const pulse = tone === "red" ? "animate-pulse" : "";

  return (
    <div
      className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md ${style.bg} ${pulse}`}
    >
      <svg width="22" height="22" viewBox="0 0 22 22" className="shrink-0">
        <circle
          cx="11"
          cy="11"
          r={RADIUS}
          fill="none"
          stroke="#DCD8CE"
          strokeWidth="2.5"
        />
        <circle
          cx="11"
          cy="11"
          r={RADIUS}
          fill="none"
          stroke={style.ring}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={dashOffset}
          transform="rotate(-90 11 11)"
        />
      </svg>
      <span className={`font-mono text-xs font-medium ${style.text}`}>
        {label}
      </span>
    </div>
  );
}
