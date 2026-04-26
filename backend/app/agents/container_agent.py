"""
Container Analyzer - scans container image or repo filesystem for vulnerabilities.
Uses trivy JSON output when installed.
"""
import json
import os
import subprocess
from typing import Dict, List


class ContainerAnalyzer:
    """Container and filesystem scanning via Trivy."""

    def run(self, repo_path: str) -> List[Dict]:
        image_ref = os.getenv("TRIVY_IMAGE")
        if image_ref:
            return self._scan_image(image_ref)
        return self._scan_filesystem(repo_path)

    def _scan_filesystem(self, repo_path: str) -> List[Dict]:
        return self._run_trivy(["trivy", "fs", repo_path, "--format", "json", "--quiet"])

    def _scan_image(self, image_ref: str) -> List[Dict]:
        return self._run_trivy(["trivy", "image", image_ref, "--format", "json", "--quiet"])

    def _run_trivy(self, cmd: List[str]) -> List[Dict]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            # trivy exits 5/1 on vulnerabilities depending on options; parse stdout anyway.
            if result.returncode not in (0, 1, 5):
                raise RuntimeError(result.stderr or result.stdout)

            raw = (result.stdout or "").strip()
            if not raw:
                return []

            payload = json.loads(raw)
            issues: List[Dict] = []
            for target in payload.get("Results", []):
                for vuln in target.get("Vulnerabilities", []) or []:
                    issues.append(
                        {
                            "type": "container",
                            "tool": "trivy",
                            "severity": (vuln.get("Severity") or "UNKNOWN").lower(),
                            "package": vuln.get("PkgName"),
                            "version": vuln.get("InstalledVersion"),
                            "fixed_version": vuln.get("FixedVersion"),
                            "cve": vuln.get("VulnerabilityID"),
                            "file": target.get("Target"),
                            "message": vuln.get("Title") or vuln.get("Description") or "Container vulnerability",
                        }
                    )
            return issues
        except FileNotFoundError:
            raise RuntimeError("Trivy is not installed. Install: https://aquasecurity.github.io/trivy/")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse trivy output")
        except Exception as e:
            raise RuntimeError(f"Trivy scan failed: {e}")
