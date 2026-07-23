import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./layout/AppShell.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import NoteGenerator from "./pages/NoteGenerator.jsx";
import TaskQueue from "./pages/TaskQueue.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/notes" element={<NoteGenerator />} />
        <Route path="/tasks" element={<TaskQueue />} />
      </Route>
    </Routes>
  );
}
