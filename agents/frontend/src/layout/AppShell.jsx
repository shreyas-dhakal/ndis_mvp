import { NavLink, Outlet } from "react-router-dom";
import DocumentSidebar from "../components/DocumentSidebar.jsx";

const NAV_ITEMS = [
  { to: "/chat", label: "Chat" },
  { to: "/notes", label: "Note Generator" },
  { to: "/tasks", label: "Tasks" },
];

export default function AppShell() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-line bg-paper sticky top-0 z-10">
        <div className="flex items-center justify-between px-6 h-16">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-sm bg-teal-500 flex items-center justify-center">
              <span className="text-paper font-display font-bold text-sm">x</span>
            </div>
            <span className="font-display font-semibold text-lg tracking-tight">
              localxai
            </span>
          </div>

          <nav className="flex gap-1">
            {NAV_ITEMS.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  `px-4 py-2 text-sm font-medium rounded-sm transition-colors ${
                    isActive
                      ? "text-teal-700 border-b-2 border-teal-600"
                      : "text-slate hover:text-ink"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="text-xs font-mono text-slate">v0.1</div>
        </div>
      </header>

      <div className="flex flex-1">
        <aside className="w-72 border-r border-line bg-paper p-4 hidden md:block">
          <DocumentSidebar />
        </aside>

        <main className="flex-1 p-6 md:p-8 max-w-5xl mx-auto w-full">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
