import type { Finding } from "../types";

interface IssueTableProps {
  findings: Finding[];
}

function severityClass(severity: Finding["severity"]) {
  return `pill pill-${severity}`;
}

export default function IssueTable({ findings }: IssueTableProps) {
  return (
    <div className="card">
      <h2>Findings</h2>
      <table className="table">
        <thead>
          <tr>
            <th>Severity</th>
            <th>Analyzer</th>
            <th>Type</th>
            <th>Repository</th>
            <th>Location</th>
            <th>Status</th>
            <th>Assignee</th>
          </tr>
        </thead>
        <tbody>
          {findings.map((finding) => (
            <tr key={finding.id}>
              <td>
                <span className={severityClass(finding.severity)}>{finding.severity}</span>
              </td>
              <td>{finding.analyzer}</td>
              <td>{finding.bugType}</td>
              <td>{finding.repository}</td>
              <td>{`${finding.file}:${finding.line}`}</td>
              <td>{finding.status}</td>
              <td>{finding.assignee}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
