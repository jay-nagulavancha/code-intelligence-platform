"""
Secrets Analyzer - scans repository history/files for leaked secrets.
Uses gitleaks JSON output when installed.
"""
import json
import subprocess
from typing import Dict, List


class SecretsAnalyzer:
    """Secret scanning via gitleaks."""

    def run(self, repo_path: str) -> List[Dict]:
        try:
            result = subprocess.run(
                [
                    "gitleaks",
                    "detect",
                    "--source",
                    repo_path,
                    "--report-format",
                    "json",
                    "--no-git",
                ],
                capture_output=True,
                text=True,
                timeout=300,
            )

            # gitleaks exits 1 when leaks are found; both 0 and 1 are valid.
            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr or result.stdout)

            raw = (result.stdout or "").strip()
            if not raw:
                return []

            findings = json.loads(raw)
            issues: List[Dict] = []
            for item in findings:
                issues.append(
                    {
                        "type": "secret",
                        "tool": "gitleaks",
                        "severity": "high",
                        "confidence": "high",
                        "file": item.get("File"),
                        "line": item.get("StartLine"),
                        "rule_id": item.get("RuleID"),
                        "message": item.get("Description") or "Potential secret detected",
                        "secret_type": item.get("RuleID"),
                    }
                )
            return issues
        except FileNotFoundError:
            raise RuntimeError("Gitleaks is not installed. Install: https://github.com/gitleaks/gitleaks")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse gitleaks output")
        except Exception as e:
            raise RuntimeError(f"Gitleaks scan failed: {e}")
