import type { DashboardSummary, Finding, RepositoryHealth } from "../types";

const API_BASE =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

const mockSummary: DashboardSummary = {
  repositories: 7,
  openFindings: 46,
  fixedLast7Days: 19,
  avgRemediationDays: 2.8,
};

const mockRepositories: RepositoryHealth[] = [
  {
    id: "1",
    fullName: "jay-nagulavancha/autocare",
    language: "Java",
    lastScanAt: "2026-04-25T18:57:11Z",
    healthScore: 62,
    critical: 0,
    high: 1,
    status: "warning",
  },
  {
    id: "2",
    fullName: "jay-nagulavancha/code-intelligence-platform",
    language: "Python",
    lastScanAt: "2026-04-25T17:12:02Z",
    healthScore: 78,
    critical: 0,
    high: 0,
    status: "healthy",
  },
];

const mockFindings: Finding[] = [
  {
    id: "f-1",
    repository: "jay-nagulavancha/autocare",
    severity: "high",
    analyzer: "security",
    bugType: "HE_EQUALS_USE_HASHCODE",
    file: "src/main/java/com/example/UserDetailsImpl.java",
    line: 30,
    status: "in_progress",
    assignee: "Jay",
    firstSeen: "2026-04-24T03:10:00Z",
  },
  {
    id: "f-2",
    repository: "jay-nagulavancha/autocare",
    severity: "medium",
    analyzer: "security",
    bugType: "EI_EXPOSE_REP",
    file: "src/main/java/com/example/User.java",
    line: 35,
    status: "new",
    assignee: "Unassigned",
    firstSeen: "2026-04-24T03:10:00Z",
  },
];

function simulate<T>(payload: T, delayMs = 200): Promise<T> {
  return new Promise((resolve) => {
    setTimeout(() => resolve(payload), delayMs);
  });
}

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}

export const api = {
  async getDashboardSummary(): Promise<DashboardSummary> {
    try {
      return await fetchJson<DashboardSummary>("/dashboard/summary");
    } catch {
      return simulate(mockSummary);
    }
  },
  async getRepositories(): Promise<RepositoryHealth[]> {
    try {
      return await fetchJson<RepositoryHealth[]>("/repos");
    } catch {
      return simulate(mockRepositories);
    }
  },
  async getFindings(query?: {
    severity?: string;
    repository?: string;
    analyzer?: string;
  }): Promise<Finding[]> {
    try {
      const params = new URLSearchParams();
      if (query?.severity) params.set("severity", query.severity);
      if (query?.repository) params.set("repository", query.repository);
      if (query?.analyzer) params.set("analyzer", query.analyzer);
      const suffix = params.toString() ? `?${params.toString()}` : "";
      return await fetchJson<Finding[]>(`/findings${suffix}`);
    } catch {
      return simulate(mockFindings);
    }
  },
};
