import { useEffect, useState } from "react";
import IssueTable from "../components/IssueTable";
import { api } from "../services/api";
import type { Finding } from "../types";

export default function Findings() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [severity, setSeverity] = useState("");
  const [analyzer, setAnalyzer] = useState("");
  const [repository, setRepository] = useState("");

  useEffect(() => {
    void api.getFindings({
      severity: severity || undefined,
      analyzer: analyzer || undefined,
      repository: repository || undefined,
    }).then(setFindings);
  }, [severity, analyzer, repository]);

  return (
    <section className="page">
      <header className="page-header">
        <h1>Findings</h1>
        <p>Triage and prioritize findings from all analyzers.</p>
      </header>
      <div className="card filters">
        <label>
          Severity
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </label>
        <label>
          Analyzer
          <select value={analyzer} onChange={(e) => setAnalyzer(e.target.value)}>
            <option value="">All</option>
            <option value="security">Security</option>
            <option value="oss">OSS</option>
            <option value="deprecation">Deprecation</option>
          </select>
        </label>
        <label>
          Repository
          <input
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
            placeholder="owner/repo"
          />
        </label>
      </div>
      <IssueTable findings={findings} />
    </section>
  );
}
