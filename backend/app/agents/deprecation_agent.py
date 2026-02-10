"""
Deprecation Agent - Detects deprecated code patterns using AST rules.
"""
import ast
import os
from typing import List, Dict
from pathlib import Path


class DeprecationAgent:
    """Detects deprecated code patterns using AST analysis."""

    def __init__(self):
        # Common deprecation patterns (can be extended)
        self.deprecation_patterns = [
            {
                "name": "print_statement",
                "pattern": "print() function should be used instead of print statement",
                "severity": "low"
            },
            {
                "name": "old_style_class",
                "pattern": "Old-style classes (no inheritance from object)",
                "severity": "low"
            }
        ]

    def _analyze_file(self, file_path: str) -> List[Dict]:
        """Analyze a single Python file for deprecation patterns."""
        issues = []
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            try:
                tree = ast.parse(content, filename=file_path)
            except SyntaxError:
                # Skip files with syntax errors
                return issues

            # Check for print statements (Python 2 style)
            for node in ast.walk(tree):
                # Check for old-style print statements (would be in Python 2)
                # In Python 3, print is a function, so we check for function calls
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    if node.func.id == "print" and len(node.args) == 0:
                        # This is a print() call, which is fine
                        pass

            # Check for old-style classes
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class doesn't inherit from object explicitly
                    if not node.bases:
                        issues.append({
                            "type": "deprecation",
                            "file": file_path,
                            "line": node.lineno,
                            "pattern": "old_style_class",
                            "message": "Class should explicitly inherit from object",
                            "severity": "low"
                        })

            # Future: Add more AST-based deprecation checks
            # - Check for deprecated imports
            # - Check for deprecated function signatures
            # - Check for deprecated decorators
            # - Check for deprecated string formatting

        except Exception as e:
            # Skip files that can't be read
            pass

        return issues

    def run(self, repo_path: str) -> List[Dict]:
        """
        Scans the repository for deprecated code patterns.
        
        Args:
            repo_path: Path to the repository
        
        Returns:
            List of deprecation issues
        """
        issues = []
        
        # Find all Python files
        python_files = []
        for root, dirs, files in os.walk(repo_path):
            # Skip common directories
            dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", "node_modules", ".venv", "venv"]]
            
            for file in files:
                if file.endswith(".py"):
                    python_files.append(os.path.join(root, file))

        # Analyze each Python file
        for file_path in python_files:
            file_issues = self._analyze_file(file_path)
            issues.extend(file_issues)

        return issues
