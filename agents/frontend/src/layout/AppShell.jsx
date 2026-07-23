import { NavLink, Outlet, useLocation } from "react-router-dom";
import DocumentSidebar from "../components/DocumentSidebar.jsx";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "◧" },
  { to: "/notes", label: "New note", icon: "✦" },
  { to: "/tasks", label: "To do", icon: "↗" },
  { to: "/chat", label: "Ask Caseload AI", icon: "⌁" },
];

export default function AppShell() {
  const location = useLocation();
  const current = NAV_ITEMS.find((item) => location.pathname.startsWith(item.to));

  return (
    <div className="min-h-screen bg-paper text-ink md:flex">
      <aside className="app-rail flex w-full flex-col bg-ink px-5 py-5 text-white md:sticky md:top-0 md:h-screen md:w-[248px] md:shrink-0">
        <div className="flex items-center gap-3">
           <div className="brand-mark"><span>c</span></div>
           <div>
             <div className="font-display text-[17px] font-semibold tracking-tight">Caseload AI</div>
             <div className="font-mono text-[9px] uppercase tracking-[0.2em] text-white/40">support notes</div>
          </div>
        </div>

        <div className="mt-14 mb-3 px-3 font-mono text-[10px] uppercase tracking-[0.2em] text-white/35">Main menu</div>
        <nav className="space-y-1">
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} className={({ isActive }) => `rail-link ${isActive ? "is-active" : ""}`}>
              <span className="rail-icon">{item.icon}</span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto hidden rounded-2xl border border-white/10 bg-white/[0.06] p-4 md:block">
          <div className="mb-3 flex items-center gap-2"><span className="status-dot" /> <span className="font-mono text-[10px] uppercase tracking-wider text-white/55">Ready to use</span></div>
           <p className="text-xs leading-relaxed text-white/55">Caseload AI helps you turn everyday support work into clear, useful records.</p>
        </div>
        <div className="mt-5 flex items-center gap-3 border-t border-white/10 pt-4">
          <div className="avatar">JS</div>
          <div><div className="text-sm font-medium">Jordan Smith</div><div className="text-[11px] text-white/40">Practice lead</div></div>
          <span className="ml-auto text-white/40">•••</span>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <header className="topbar flex items-center justify-between border-b border-line px-5 py-4 md:px-10">
          <div className="flex items-center gap-3">
            <div className="hidden h-10 w-10 items-center justify-center rounded-xl bg-teal-50 text-teal-700 sm:flex" aria-hidden="true">✦</div>
            <div>
              <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate">Workspace / {current?.label || "Overview"}</div>
              <div className="mt-1 flex items-center gap-2">
                <div className="font-display text-sm font-semibold text-ink">Thursday, 23 July 2026</div>
                <span className="hidden rounded-full bg-ochre-50 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-ochre-600 md:inline">Today</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3"><span className="hidden rounded-full bg-white px-3 py-1.5 font-mono text-[10px] text-slate shadow-sm sm:block">READY TO USE</span><button className="icon-button" aria-label="Notifications">◌</button></div>
        </header>
        <div className="flex min-w-0 flex-1">
          <main className="mx-auto w-full max-w-[1240px] flex-1 p-5 md:p-10"><Outlet /><div className="surface mt-6 p-4 xl:hidden"><DocumentSidebar /></div></main>
          <aside className="hidden w-[290px] shrink-0 border-l border-line bg-[#eeeee8] px-5 py-8 xl:block">
             <div className="mb-4"><div className="eyebrow">Workspace context</div><h2 className="mt-1 font-display text-lg font-semibold">Your files</h2><p className="mt-1 text-xs leading-5 text-slate">Add notes and files here so Caseload AI can help you find the right detail.</p></div>
            <div className="surface min-h-[420px] p-4"><DocumentSidebar /></div>
          </aside>
        </div>
      </div>
    </div>
  );
}
