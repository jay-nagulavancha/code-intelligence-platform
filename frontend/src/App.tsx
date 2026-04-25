import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import Repositories from "./pages/Repositories";
import Findings from "./pages/Findings";

function linkClassName({ isActive }: { isActive: boolean }) {
  return isActive ? "nav-link nav-link-active" : "nav-link";
}

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1 className="brand">Code Intel</h1>
        <nav className="nav">
          <NavLink to="/dashboard" className={linkClassName}>
            Overview
          </NavLink>
          <NavLink to="/repositories" className={linkClassName}>
            Repositories
          </NavLink>
          <NavLink to="/findings" className={linkClassName}>
            Findings
          </NavLink>
        </nav>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/repositories" element={<Repositories />} />
          <Route path="/findings" element={<Findings />} />
        </Routes>
      </main>
    </div>
  );
}
