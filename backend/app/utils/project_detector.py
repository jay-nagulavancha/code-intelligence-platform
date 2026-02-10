"""
Project Language Detector - Detects programming languages in a project.
"""
import os
from typing import List, Optional, Dict
from pathlib import Path


class ProjectDetector:
    """Detects programming languages and project types."""

    # Language indicators
    LANGUAGE_INDICATORS = {
        "python": [
            "requirements.txt", "setup.py", "pyproject.toml", "Pipfile",
            "poetry.lock", "__init__.py", ".python-version"
        ],
        "java": [
            "pom.xml", "build.gradle", "build.gradle.kts", ".classpath",
            ".project", "pom.xml", "build.xml", ".java"
        ],
        "javascript": [
            "package.json", "yarn.lock", "package-lock.json", ".js",
            "tsconfig.json", "webpack.config.js"
        ],
        "go": [
            "go.mod", "go.sum", "Gopkg.toml", ".go"
        ],
        "rust": [
            "Cargo.toml", "Cargo.lock", ".rs"
        ],
        "csharp": [
            ".csproj", ".sln", ".cs"
        ],
        "cpp": [
            "CMakeLists.txt", "Makefile", ".cpp", ".hpp", ".cxx"
        ]
    }

    @staticmethod
    def detect_languages(repo_path: str) -> List[str]:
        """
        Detect programming languages in a repository.
        
        Args:
            repo_path: Path to the repository
        
        Returns:
            List of detected languages (e.g., ["python", "java"])
        """
        detected = set()
        
        if not os.path.exists(repo_path):
            return []
        
        # Check for language-specific files
        for language, indicators in ProjectDetector.LANGUAGE_INDICATORS.items():
            for indicator in indicators:
                # Check root directory
                if os.path.exists(os.path.join(repo_path, indicator)):
                    detected.add(language)
                    break
                
                # Check for file extensions in common directories
                if indicator.startswith("."):
                    # Search for files with this extension
                    for root, dirs, files in os.walk(repo_path):
                        # Skip hidden directories and common ignore dirs
                        dirs[:] = [d for d in dirs if not d.startswith(".") 
                                  and d not in ["node_modules", "__pycache__", "target", "build"]]
                        
                        for file in files:
                            if file.endswith(indicator):
                                detected.add(language)
                                break
                        if language in detected:
                            break
        
        # Check for Java source files specifically
        java_dirs = ["src/main/java", "src"]
        for java_dir in java_dirs:
            java_path = os.path.join(repo_path, java_dir)
            if os.path.exists(java_path):
                for root, dirs, files in os.walk(java_path):
                    if any(f.endswith(".java") for f in files):
                        detected.add("java")
                        break
                if "java" in detected:
                    break
        
        # Check for Python source files
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith(".") 
                      and d not in ["node_modules", "__pycache__", "venv", ".venv"]]
            if any(f.endswith(".py") for f in files):
                detected.add("python")
                break
        
        return sorted(list(detected))

    @staticmethod
    def get_primary_language(repo_path: str) -> Optional[str]:
        """
        Get the primary programming language.
        
        Args:
            repo_path: Path to the repository
        
        Returns:
            Primary language or None
        """
        languages = ProjectDetector.detect_languages(repo_path)
        
        # Priority order
        priority = ["java", "python", "javascript", "go", "rust", "csharp", "cpp"]
        
        for lang in priority:
            if lang in languages:
                return lang
        
        return languages[0] if languages else None

    @staticmethod
    def get_project_info(repo_path: str) -> Dict[str, any]:
        """
        Get comprehensive project information.
        
        Args:
            repo_path: Path to the repository
        
        Returns:
            Dictionary with project information
        """
        languages = ProjectDetector.detect_languages(repo_path)
        primary = ProjectDetector.get_primary_language(repo_path)
        
        # Detect build tools
        build_tools = []
        if os.path.exists(os.path.join(repo_path, "pom.xml")):
            build_tools.append("maven")
        if os.path.exists(os.path.join(repo_path, "build.gradle")) or \
           os.path.exists(os.path.join(repo_path, "build.gradle.kts")):
            build_tools.append("gradle")
        if os.path.exists(os.path.join(repo_path, "package.json")):
            build_tools.append("npm")
        if os.path.exists(os.path.join(repo_path, "requirements.txt")) or \
           os.path.exists(os.path.join(repo_path, "pyproject.toml")):
            build_tools.append("pip")
        
        return {
            "languages": languages,
            "primary_language": primary,
            "build_tools": build_tools,
            "is_multi_language": len(languages) > 1
        }
