"""
Project Builder - Automatically builds projects before scanning.
Supports Maven and Gradle for Java projects.
Detects required Java version and selects the correct JDK.
Works on macOS and Linux (including Docker containers).
"""
import subprocess
import os
import re
import sys
import xml.etree.ElementTree as ET
from typing import Optional, Dict


class ProjectBuilder:
    """Detects build system and compiles the project."""

    @staticmethod
    def detect_build_system(repo_path: str) -> Optional[str]:
        """
        Detect the build system used by the project.
        
        Returns:
            "maven", "gradle", "gradle_wrapper", or None
        """
        if os.path.exists(os.path.join(repo_path, "pom.xml")):
            return "maven"
        if os.path.exists(os.path.join(repo_path, "gradlew")):
            return "gradle_wrapper"
        if os.path.exists(os.path.join(repo_path, "build.gradle")) or \
           os.path.exists(os.path.join(repo_path, "build.gradle.kts")):
            return "gradle"
        return None

    @staticmethod
    def _detect_required_java_version(repo_path: str) -> Optional[int]:
        """
        Try to determine which Java version the project needs.
        Inspects pom.xml properties, maven-compiler-plugin, and build.gradle.
        Returns the major version number (e.g. 17) or None.
        """
        pom_path = os.path.join(repo_path, "pom.xml")
        if os.path.exists(pom_path):
            try:
                tree = ET.parse(pom_path)
                root = tree.getroot()
                ns = ""
                # Handle Maven XML namespace
                m = re.match(r"\{(.+)\}", root.tag)
                if m:
                    ns = m.group(1)
                nsmap = {"m": ns} if ns else {}

                def find_text(xpath_no_ns: str) -> Optional[str]:
                    """Search with and without namespace."""
                    if nsmap:
                        parts = xpath_no_ns.split("/")
                        ns_xpath = "/".join(f"m:{p}" for p in parts)
                        el = root.find(ns_xpath, nsmap)
                    else:
                        el = root.find(xpath_no_ns)
                    return el.text.strip() if el is not None and el.text else None

                # Check common property names
                for prop in [
                    "properties/java.version",
                    "properties/maven.compiler.release",
                    "properties/maven.compiler.source",
                    "properties/maven.compiler.target",
                ]:
                    val = find_text(prop)
                    if val:
                        version = re.sub(r"^1\.", "", val)  # "1.8" -> "8"
                        try:
                            return int(version)
                        except ValueError:
                            continue
            except Exception:
                pass

        # Check build.gradle
        for gradle_file in ["build.gradle", "build.gradle.kts"]:
            gradle_path = os.path.join(repo_path, gradle_file)
            if os.path.exists(gradle_path):
                try:
                    with open(gradle_path, "r") as f:
                        content = f.read()
                    m = re.search(
                        r"(?:sourceCompatibility|targetCompatibility|java\.toolchain\.languageVersion)"
                        r"\s*[=.]\s*['\"]?(\d+)",
                        content
                    )
                    if m:
                        return int(m.group(1))
                except Exception:
                    pass

        return None

    @staticmethod
    def _resolve_java_home(required_version: Optional[int]) -> Optional[str]:
        """
        Find the correct JAVA_HOME for the required version.
        Supports macOS (/usr/libexec/java_home) and Linux (/usr/lib/jvm).
        Returns the JAVA_HOME path or None.
        """
        if required_version is None:
            return None

        # If JAVA_HOME is already set and matches, use it
        current = os.environ.get("JAVA_HOME")
        if current and os.path.isdir(current):
            javac = os.path.join(current, "bin", "javac")
            if os.path.exists(javac):
                try:
                    result = subprocess.run(
                        [javac, "-version"],
                        capture_output=True, text=True, timeout=10,
                    )
                    ver_text = result.stderr.strip() or result.stdout.strip()
                    if str(required_version) in ver_text:
                        return current
                except Exception:
                    pass

        # macOS: use /usr/libexec/java_home
        if sys.platform == "darwin":
            try:
                result = subprocess.run(
                    ["/usr/libexec/java_home", "-v", str(required_version)],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except Exception:
                pass

            jvm_base = "/Library/Java/JavaVirtualMachines"
            if os.path.isdir(jvm_base):
                for entry in os.listdir(jvm_base):
                    if str(required_version) in entry:
                        candidate = os.path.join(jvm_base, entry, "Contents", "Home")
                        if os.path.isdir(candidate):
                            return candidate

        # Linux: scan /usr/lib/jvm (Debian/Ubuntu, Docker containers)
        else:
            jvm_base = "/usr/lib/jvm"
            if os.path.isdir(jvm_base):
                # Prefer exact match, then partial
                for entry in sorted(os.listdir(jvm_base), reverse=True):
                    if str(required_version) in entry:
                        candidate = os.path.join(jvm_base, entry)
                        if os.path.isdir(candidate) and os.path.exists(
                            os.path.join(candidate, "bin", "javac")
                        ):
                            return candidate
                # Fallback: default-java symlink
                default = os.path.join(jvm_base, "default-java")
                if os.path.isdir(default):
                    return default

        return None

    @staticmethod
    def _build_env(repo_path: str) -> Dict[str, str]:
        """Build an environment dict with the correct JAVA_HOME if needed."""
        env = os.environ.copy()
        required = ProjectBuilder._detect_required_java_version(repo_path)
        if required:
            java_home = ProjectBuilder._resolve_java_home(required)
            if java_home:
                env["JAVA_HOME"] = java_home
                env["PATH"] = os.path.join(java_home, "bin") + os.pathsep + env.get("PATH", "")
        return env

    @staticmethod
    def build(repo_path: str, build_system: Optional[str] = None) -> Dict[str, any]:
        """
        Build the project.

        Args:
            repo_path: Path to the repository root
            build_system: Override build system detection

        Returns:
            Dict with keys: success (bool), build_system (str), message (str)
        """
        if build_system is None:
            build_system = ProjectBuilder.detect_build_system(repo_path)

        if build_system is None:
            return {
                "success": False,
                "build_system": None,
                "message": "No supported build system detected (pom.xml / build.gradle / gradlew)"
            }

        if build_system == "maven":
            return ProjectBuilder._build_maven(repo_path)
        elif build_system in ("gradle", "gradle_wrapper"):
            return ProjectBuilder._build_gradle(repo_path)
        else:
            return {
                "success": False,
                "build_system": build_system,
                "message": f"Unsupported build system: {build_system}"
            }

    @staticmethod
    def _build_maven(repo_path: str) -> Dict[str, any]:
        """Build a Maven project, selecting the correct Java version."""
        env = ProjectBuilder._build_env(repo_path)
        java_home = env.get("JAVA_HOME", "system default")

        # Prefer the Maven wrapper if present
        wrapper = os.path.join(repo_path, "mvnw")
        if os.path.exists(wrapper):
            os.chmod(wrapper, 0o755)
            cmd = [wrapper, "compile", "-q", "-DskipTests"]
        else:
            cmd = ["mvn", "compile", "-q", "-DskipTests"]

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "build_system": "maven",
                    "message": f"Maven build succeeded (JAVA_HOME={java_home})"
                }
            else:
                err = (result.stderr or result.stdout or "unknown error")
                tail = "\n".join(err.strip().splitlines()[-20:])
                return {
                    "success": False,
                    "build_system": "maven",
                    "message": f"Maven build failed (JAVA_HOME={java_home}):\n{tail}"
                }
        except FileNotFoundError:
            return {
                "success": False,
                "build_system": "maven",
                "message": "Maven (mvn) is not installed or not in PATH"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "build_system": "maven",
                "message": "Maven build timed out (>10 min)"
            }

    @staticmethod
    def _build_gradle(repo_path: str) -> Dict[str, any]:
        """Build a Gradle project, selecting the correct Java version."""
        env = ProjectBuilder._build_env(repo_path)
        java_home = env.get("JAVA_HOME", "system default")

        wrapper = os.path.join(repo_path, "gradlew")
        if os.path.exists(wrapper):
            os.chmod(wrapper, 0o755)
            cmd = [wrapper, "compileJava", "-q", "-x", "test"]
        else:
            cmd = ["gradle", "compileJava", "-q", "-x", "test"]

        try:
            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=600,
                env=env,
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "build_system": "gradle",
                    "message": f"Gradle build succeeded (JAVA_HOME={java_home})"
                }
            else:
                err = (result.stderr or result.stdout or "unknown error")
                tail = "\n".join(err.strip().splitlines()[-20:])
                return {
                    "success": False,
                    "build_system": "gradle",
                    "message": f"Gradle build failed (JAVA_HOME={java_home}):\n{tail}"
                }
        except FileNotFoundError:
            return {
                "success": False,
                "build_system": "gradle",
                "message": "Gradle is not installed or not in PATH"
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "build_system": "gradle",
                "message": "Gradle build timed out (>10 min)"
            }
