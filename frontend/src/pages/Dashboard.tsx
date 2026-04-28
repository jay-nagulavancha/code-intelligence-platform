import { useEffect, useState } from "react";
import StatCard from "../components/StatCard";
import { api } from "../services/api";
import type { DashboardSummary } from "../types";

export default function Dashboard() {
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  useEffect(() => {
    void api.getDashboardSummary().then(setSummary);
  }, []);

  if (!summary) {
    return <p>Loading dashboard...</p>;
  }

  return (
    <section className="page">
      <header className="page-header">
        <h1>Overview</h1>
        <p>Security and remediation health across repositories.</p>
      </header>
      <div className="grid grid-4">
        <StatCard title="Repositories" value={summary.repositories} />
        <StatCard title="Open Findings" value={summary.openFindings} />
        <StatCard title="Fixed (7d)" value={summary.fixedLast7Days} />
        <StatCard title="Avg Remediation" value={`${summary.avgRemediationDays} days`} />
      </div>
      <div className="grid grid-2">
        <article className="card">
          <h2>Trend Snapshot</h2>
          <p>New vs fixed findings chart placeholder (wire to `/api/dashboard/trends`).</p>
        </article>
        <article className="card">
          <h2>Recent Activity</h2>
          <p>Activity feed placeholder (wire to `/api/dashboard/activity`).</p>
        </article>
      </div>
    </section>
  );
}
