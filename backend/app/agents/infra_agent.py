"""
Infrastructure Analyzer - scans IaC manifests for security misconfiguration.
Uses checkov JSON output when installed.
"""
import json
import subprocess
from typing import Dict, List


class InfraAnalyzer:
    """IaC scanning via Checkov."""

    def run(self, repo_path: str) -> List[Dict]:
        try:
            result = subprocess.run(
                [
                    "checkov",
                    "-d",
                    repo_path,
                    "-o",
                    "json",
                    "--quiet",
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )

            # checkov can return 1 when checks fail; still parseable/valid.
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr or result.stdout)

            raw = (result.stdout or "").strip()
            if not raw:
                return []

            payload = json.loads(raw)
            if isinstance(payload, dict):
                reports = [payload]
            else:
                reports = payload

            issues: List[Dict] = []
            for report in reports:
                failed_checks = report.get("results", {}).get("failed_checks", [])
                for check in failed_checks:
                    severity = (check.get("severity") or "MEDIUM").lower()
                    issues.append(
                        {
                            "type": "infra",
                            "tool": "checkov",
                            "severity": severity,
                            "file": check.get("file_path"),
                            "line": (check.get("file_line_range") or [None])[0],
                            "check_id": check.get("check_id"),
                            "message": check.get("check_name") or "Infrastructure misconfiguration",
                            "resource": check.get("resource"),
                        }
                    )
            return issues
        except FileNotFoundError:
            raise RuntimeError("Checkov is not installed. Install: pip install checkov")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse checkov output")
        except Exception as e:
            raise RuntimeError(f"Checkov scan failed: {e}")
