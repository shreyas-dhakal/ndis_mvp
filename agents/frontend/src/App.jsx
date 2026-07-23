import { Routes, Route, Navigate } from "react-router-dom";
import AppShell from "./layout/AppShell.jsx";
import ChatPage from "./pages/ChatPage.jsx";
import NoteGenerator from "./pages/NoteGenerator.jsx";
import TaskQueue from "./pages/TaskQueue.jsx";
import Landing from "./pages/Landing.jsx";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route element={<AppShell />}>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/notes" element={<NoteGenerator />} />
        <Route path="/tasks" element={<TaskQueue />} />
      </Route>
    </Routes>
  );
}
