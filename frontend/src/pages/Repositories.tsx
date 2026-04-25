import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { RepositoryHealth } from "../types";

export default function Repositories() {
  const [repositories, setRepositories] = useState<RepositoryHealth[]>([]);

  useEffect(() => {
    void api.getRepositories().then(setRepositories);
  }, []);

  return (
    <section className="page">
      <header className="page-header">
        <h1>Repositories</h1>
        <p>Track health, risk and latest scan posture by repository.</p>
      </header>
      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Repository</th>
              <th>Language</th>
              <th>Health Score</th>
              <th>Critical</th>
              <th>High</th>
              <th>Last Scan</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {repositories.map((repo) => (
              <tr key={repo.id}>
                <td>{repo.fullName}</td>
                <td>{repo.language}</td>
                <td>{repo.healthScore}</td>
                <td>{repo.critical}</td>
                <td>{repo.high}</td>
                <td>{new Date(repo.lastScanAt).toLocaleString()}</td>
                <td>
                  <span className={`pill pill-${repo.status}`}>{repo.status}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
