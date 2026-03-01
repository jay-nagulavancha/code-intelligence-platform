"""
Security Analyzer - Multi-language security vulnerability scanning.
Supports Python (Bandit) and Java (SpotBugs).
Automatically builds Java projects before scanning.
"""
import subprocess
import json
import os
from typing import List, Dict, Optional
from app.utils.project_detector import ProjectDetector
from app.utils.project_builder import ProjectBuilder


class SecurityAnalyzer:
    """
    Multi-language security vulnerability scanner.
    Automatically detects project language and uses appropriate tool.
    Auto-builds Java projects when compiled classes are missing.
    """

    def __init__(self):
        self.detector = ProjectDetector()
        self.builder = ProjectBuilder()

    def _detect_language(self, repo_path: str) -> str:
        """Detect primary language of the project."""
        primary = self.detector.get_primary_language(repo_path)
        if primary:
            return primary
        
        # Default to python if cannot detect
        return "python"

    def _scan_python(self, repo_path: str) -> List[Dict]:
        """Scan Python project using Bandit."""
        try:
            result = subprocess.run(
                [
                    "bandit",
                    "-r",
                    repo_path,
                    "-f",
                    "json"
                ],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode not in (0, 1):
                raise RuntimeError(result.stderr)

            data = json.loads(result.stdout)
            issues = []

            for item in data.get("results", []):
                issues.append({
                    "type": "security",
                    "language": "python",
                    "tool": "bandit",
                    "severity": item.get("issue_severity"),
                    "confidence": item.get("issue_confidence"),
                    "file": item.get("filename"),
                    "line": item.get("line_number"),
                    "message": item.get("issue_text"),
                    "cwe": item.get("issue_cwe", {}).get("id"),
                    "test_id": item.get("test_id"),
                })

            return issues

        except FileNotFoundError:
            raise RuntimeError("Bandit is not installed. Run: pip install bandit")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse Bandit output")
        except Exception as e:
            raise RuntimeError(f"Bandit scan failed: {str(e)}")

    def _find_class_dirs(self, repo_path: str) -> List[str]:
        """Locate compiled .class directories in the project."""
        class_dirs = []
        skip = {".git", "node_modules", ".idea", ".spotbugs-output"}

        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in skip]
            if "target" in root or "build" in root:
                classes_dir = os.path.join(root, "classes")
                if os.path.exists(classes_dir):
                    class_dirs.append(classes_dir)

        if not class_dirs:
            for root, dirs, files in os.walk(repo_path):
                dirs[:] = [d for d in dirs if d not in skip]
                if any(f.endswith(".class") for f in files):
                    class_dirs.append(root)
                    break

        return class_dirs

    def _scan_java(self, repo_path: str, auto_build: bool = True) -> List[Dict]:
        """
        Scan Java project using SpotBugs.
        Automatically builds the project if compiled classes are missing.
        """
        try:
            # Check if SpotBugs is available
            result = subprocess.run(
                ["spotbugs", "-version"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                result = subprocess.run(
                    ["which", "spotbugs"],
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    raise RuntimeError(
                        "SpotBugs is not installed. "
                        "Install from: https://spotbugs.github.io/ "
                        "Or use: brew install spotbugs (macOS)"
                    )

            # Create output directory
            output_dir = os.path.join(repo_path, ".spotbugs-output")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, "spotbugs.xml")

            # Look for compiled classes
            class_dirs = self._find_class_dirs(repo_path)

            # Auto-build if no classes found
            if not class_dirs and auto_build:
                build_result = self.builder.build(repo_path)
                if build_result["success"]:
                    class_dirs = self._find_class_dirs(repo_path)
                else:
                    return [{
                        "type": "security",
                        "language": "java",
                        "tool": "spotbugs",
                        "severity": "warning",
                        "message": f"Auto-build failed: {build_result['message']}",
                        "file": None,
                        "line": None
                    }]

            if not class_dirs:
                return [{
                    "type": "security",
                    "language": "java",
                    "tool": "spotbugs",
                    "severity": "info",
                    "message": (
                        "Java project detected but no compiled classes found "
                        "even after attempting auto-build. "
                        "Please build the project manually (mvn compile or ./gradlew build)"
                    ),
                    "file": None,
                    "line": None
                }]

            # Run SpotBugs on found class directories
            spotbugs_cmd = [
                "spotbugs",
                "-textui",
                "-xml:withMessages",
                "-output", output_file
            ] + class_dirs

            result = subprocess.run(
                spotbugs_cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=repo_path
            )

            if result.returncode > 3:
                raise RuntimeError(f"SpotBugs failed: {result.stderr}")

            # Parse XML output
            issues = []
            if os.path.exists(output_file):
                try:
                    import xml.etree.ElementTree as ET
                    tree = ET.parse(output_file)
                    root = tree.getroot()

                    for bug in root.findall(".//BugInstance"):
                        issue = {
                            "type": "security",
                            "language": "java",
                            "tool": "spotbugs",
                            "category": bug.get("category", "unknown"),
                            "bug_type": bug.get("type", "unknown"),
                            "message": bug.findtext("ShortMessage", ""),
                            "file": None,
                            "line": None
                        }

                        source_line = bug.find(".//SourceLine")
                        if source_line is not None:
                            issue["file"] = source_line.get(
                                "sourcepath", source_line.get("relSourcepath")
                            )
                            issue["line"] = source_line.get(
                                "start", source_line.get("line")
                            )

                        priority = bug.get("priority", "3")
                        if priority == "1":
                            issue["severity"] = "high"
                        elif priority == "2":
                            issue["severity"] = "medium"
                        else:
                            issue["severity"] = "low"

                        issues.append(issue)
                except Exception as e:
                    issues.append({
                        "type": "security",
                        "language": "java",
                        "tool": "spotbugs",
                        "severity": "info",
                        "message": f"SpotBugs scan completed but failed to parse results: {str(e)}",
                        "file": None,
                        "line": None
                    })

            # Cleanup
            try:
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
            except Exception:
                pass

            return issues

        except FileNotFoundError:
            raise RuntimeError(
                "SpotBugs is not installed. "
                "Install from: https://spotbugs.github.io/ "
                "Or use: brew install spotbugs (macOS) or download from GitHub releases"
            )
        except Exception as e:
            raise RuntimeError(f"SpotBugs scan failed: {str(e)}")

    def run(self, repo_path: str, language: Optional[str] = None) -> List[Dict]:
        """
        Run security scan on the repository.
        
        Args:
            repo_path: Path to the repository
            language: Optional language override (auto-detected if not provided)
        
        Returns:
            List of security issues
        """
        if language is None:
            language = self._detect_language(repo_path)
        
        language = language.lower()
        
        if language == "python":
            return self._scan_python(repo_path)
        elif language == "java":
            return self._scan_java(repo_path)
        else:
            # Try Python as fallback, or return empty if unsupported
            if language not in ["python", "java"]:
                return [{
                    "type": "security",
                    "language": language,
                    "severity": "info",
                    "message": f"Security scanning not yet supported for {language}. Supported languages: Python (Bandit), Java (SpotBugs)",
                    "file": None,
                    "line": None
                }]
            return []
