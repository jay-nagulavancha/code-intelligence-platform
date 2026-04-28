export type Severity = "critical" | "high" | "medium" | "low";

export interface DashboardSummary {
  repositories: number;
  openFindings: number;
  fixedLast7Days: number;
  avgRemediationDays: number;
}

export interface RepositoryHealth {
  id: string;
  fullName: string;
  language: string;
  lastScanAt: string;
  healthScore: number;
  critical: number;
  high: number;
  status: "healthy" | "warning" | "critical";
}

export interface Finding {
  id: string;
  repository: string;
  severity: Severity;
  analyzer: string;
  bugType: string;
  file: string;
  line: number;
  status: "new" | "in_progress" | "fixed" | "accepted";
  assignee: string;
  firstSeen: string;
}
