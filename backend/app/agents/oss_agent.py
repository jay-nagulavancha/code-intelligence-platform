"""
OSS Agent - Multi-language open source dependency scanning.
Supports Python (pip-licenses) and Java (OWASP Dependency-Check).
Scans dependencies for licenses and known vulnerabilities.
Automatically builds Java projects before scanning.
"""
import subprocess
import json
import os
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from app.utils.project_detector import ProjectDetector
from app.utils.project_builder import ProjectBuilder


class OSSAgent:
    """
    Multi-language OSS dependency scanner.
    Scans dependencies for licenses and known vulnerabilities.
    Auto-builds Java projects when needed.
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
        """Scan Python dependencies using pip-licenses."""
        try:
            result = subprocess.run(
                [
                    "pip-licenses",
                    "--format=json"
                ],
                cwd=repo_path,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(result.stderr)

            data = json.loads(result.stdout)
            issues = []

            for dep in data:
                issues.append({
                    "type": "oss",
                    "language": "python",
                    "tool": "pip-licenses",
                    "package": dep.get("Name"),
                    "version": dep.get("Version"),
                    "license": dep.get("License"),
                    "url": dep.get("URL"),
                    "vulnerabilities": []  # pip-licenses doesn't check vulnerabilities
                })

            return issues

        except FileNotFoundError:
            raise RuntimeError("pip-licenses not installed. Run: pip install pip-licenses")
        except json.JSONDecodeError:
            raise RuntimeError("Failed to parse pip-licenses output")
        except Exception as e:
            raise RuntimeError(f"Python dependency scan failed: {str(e)}")

    def _scan_java_maven(self, repo_path: str, auto_build: bool = True) -> List[Dict]:
        """
        Scan Java Maven dependencies using OWASP Dependency-Check.
        Automatically builds the project first so dependency JARs are resolved.
        """
        # Auto-build so that dependency JARs are downloaded into target/
        if auto_build:
            build_result = self.builder.build(repo_path)
            if not build_result["success"]:
                return [{
                    "type": "oss",
                    "language": "java",
                    "tool": "dependency-check",
                    "severity": "warning",
                    "message": f"Auto-build failed — dependency scan may be incomplete: {build_result['message']}",
                    "package": None,
                    "version": None
                }]

        try:
            # Check if dependency-check is available
            try:
                result = subprocess.run(
                    ["dependency-check", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            except FileNotFoundError:
                # Try alternative paths
                dep_check_paths = [
                    "/usr/local/bin/dependency-check.sh",
                    "/opt/homebrew/bin/dependency-check.sh",
                    os.path.expanduser("~/dependency-check/bin/dependency-check.sh"),
                ]
                dep_check_found = any(os.path.exists(path) for path in dep_check_paths)
                
                if not dep_check_found:
                    raise RuntimeError(
                        "OWASP Dependency-Check is not installed. "
                        "Install from: https://owasp.org/www-project-dependency-check/ "
                        "macOS: brew install dependency-check"
                    )
            
            # Create output directory
            output_dir = os.path.join(repo_path, ".dependency-check-output")
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, "dependency-check-report.json")
            
            # Check if pom.xml exists
            pom_path = os.path.join(repo_path, "pom.xml")
            if not os.path.exists(pom_path):
                return [{
                    "type": "oss",
                    "language": "java",
                    "tool": "dependency-check",
                    "severity": "info",
                    "message": "Java project detected but pom.xml not found. Only Maven projects are currently supported.",
                    "package": None,
                    "version": None
                }]
            
            # Run dependency-check
            dep_check_cmd = [
                "dependency-check.sh" if os.name != 'nt' else "dependency-check.bat",
                "--project", "Maven Project",
                "--scan", repo_path,
                "--format", "JSON",
                "--out", output_dir,
                "--enableExperimental",  # Enable experimental analyzers
                "--failOnCVSS", "0"  # Don't fail on any CVSS score
            ]
            
            result = subprocess.run(
                dep_check_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes timeout
            )
            
            # dependency-check returns 0 for success, non-zero for vulnerabilities found
            # Both are valid - we want the report either way
            issues = []
            
            if os.path.exists(output_file):
                try:
                    with open(output_file, 'r') as f:
                        report_data = json.load(f)
                    
                    dependencies = report_data.get("dependencies", [])
                    
                    for dep in dependencies:
                        package_info = {
                            "type": "oss",
                            "language": "java",
                            "tool": "dependency-check",
                            "package": dep.get("fileName", "Unknown"),
                            "version": dep.get("version", "Unknown"),
                            "file_path": dep.get("filePath", ""),
                            "vulnerabilities": []
                        }
                        
                        # Extract vulnerabilities
                        vulnerabilities = dep.get("vulnerabilities", [])
                        for vuln in vulnerabilities:
                            cve = vuln.get("name", "")
                            severity = vuln.get("severity", "UNKNOWN")
                            cvss_v2 = vuln.get("cvssv2", {})
                            cvss_v3 = vuln.get("cvssv3", {})
                            
                            # Determine severity from CVSS
                            cvss_score = 0.0
                            if cvss_v3:
                                cvss_score = float(cvss_v3.get("baseScore", 0))
                            elif cvss_v2:
                                cvss_score = float(cvss_v2.get("score", 0))
                            
                            # Map CVSS to severity
                            if cvss_score >= 9.0:
                                severity_level = "critical"
                            elif cvss_score >= 7.0:
                                severity_level = "high"
                            elif cvss_score >= 4.0:
                                severity_level = "medium"
                            elif cvss_score > 0:
                                severity_level = "low"
                            else:
                                severity_level = "info"
                            
                            package_info["vulnerabilities"].append({
                                "cve": cve,
                                "severity": severity_level,
                                "cvss_score": cvss_score,
                                "cvss_v2": cvss_v2,
                                "cvss_v3": cvss_v3,
                                "description": vuln.get("description", ""),
                                "references": vuln.get("references", [])
                            })
                        
                        # Only include packages with vulnerabilities or for license info
                        if package_info["vulnerabilities"] or True:  # Include all for license tracking
                            issues.append(package_info)
                
                except Exception as e:
                    issues.append({
                        "type": "oss",
                        "language": "java",
                        "tool": "dependency-check",
                        "severity": "error",
                        "message": f"Failed to parse dependency-check report: {str(e)}",
                        "package": None,
                        "version": None
                    })
            
            # Cleanup
            try:
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
            except:
                pass
            
            return issues

        except FileNotFoundError:
            raise RuntimeError(
                "OWASP Dependency-Check is not installed. "
                "Install from: https://owasp.org/www-project-dependency-check/ "
                "macOS: brew install dependency-check"
            )
        except Exception as e:
            raise RuntimeError(f"Dependency-Check scan failed: {str(e)}")

    def _scan_java_gradle(self, repo_path: str) -> List[Dict]:
        """Scan Java Gradle dependencies using OWASP Dependency-Check."""
        # For now, use the same dependency-check approach
        # Gradle projects can be scanned similarly
        return self._scan_java_maven(repo_path)

    def run(self, repo_path: str, language: Optional[str] = None) -> List[Dict]:
        """
        Run OSS dependency scan on the repository.
        
        Args:
            repo_path: Path to the repository
            language: Optional language override (auto-detected if not provided)
        
        Returns:
            List of dependency issues with licenses and vulnerabilities
        """
        if language is None:
            language = self._detect_language(repo_path)
        
        language = language.lower()
        
        if language == "python":
            return self._scan_python(repo_path)
        elif language == "java":
            # Check for Maven or Gradle
            if os.path.exists(os.path.join(repo_path, "pom.xml")):
                return self._scan_java_maven(repo_path)
            elif os.path.exists(os.path.join(repo_path, "build.gradle")) or \
                 os.path.exists(os.path.join(repo_path, "build.gradle.kts")):
                return self._scan_java_gradle(repo_path)
            else:
                return [{
                    "type": "oss",
                    "language": "java",
                    "severity": "info",
                    "message": "Java project detected but no build file found (pom.xml or build.gradle)",
                    "package": None,
                    "version": None
                }]
        else:
            # Return info message for unsupported languages
            return [{
                "type": "oss",
                "language": language,
                "severity": "info",
                "message": f"OSS dependency scanning not yet supported for {language}. Supported languages: Python (pip-licenses), Java (OWASP Dependency-Check)",
                "package": None,
                "version": None
            }]