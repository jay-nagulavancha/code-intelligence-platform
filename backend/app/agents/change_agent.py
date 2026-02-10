"""
Change Agent - Analyzes code changes using git diff.
"""
import subprocess
import json
from typing import List, Dict, Optional


class ChangeAgent:
    """Analyzes code changes using git diff."""

    def run(
        self, 
        repo_path: str, 
        base_ref: Optional[str] = None, 
        head_ref: Optional[str] = None
    ) -> List[Dict]:
        """
        Analyzes code changes using git diff.
        
        Args:
            repo_path: Path to the repository
            base_ref: Base reference (branch/commit), defaults to main/master
            head_ref: Head reference (branch/commit), defaults to HEAD
        
        Returns:
            List of change issues with file paths, line numbers, and change types
        """
        try:
            # Determine base and head refs
            if base_ref is None:
                # Try to find default branch
                try:
                    result = subprocess.run(
                        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
                        cwd=repo_path,
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        base_ref = result.stdout.strip().split("/")[-1]
                    else:
                        # Try common branch names
                        for branch in ["main", "master", "develop"]:
                            result = subprocess.run(
                                ["git", "rev-parse", "--verify", f"origin/{branch}"],
                                cwd=repo_path,
                                capture_output=True
                            )
                            if result.returncode == 0:
                                base_ref = branch
                                break
                        if base_ref is None:
                            base_ref = "HEAD~1"  # Fallback to previous commit
                except Exception:
                    base_ref = "HEAD~1"

            if head_ref is None:
                head_ref = "HEAD"

            # Get git diff
            result = subprocess.run(
                ["git", "diff", "--numstat", base_ref, head_ref],
                cwd=repo_path,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise RuntimeError(f"Git diff failed: {result.stderr}")

            changes = []
            diff_lines = result.stdout.strip().split("\n")

            for line in diff_lines:
                if not line.strip():
                    continue
                
                parts = line.split("\t")
                if len(parts) >= 3:
                    additions = int(parts[0]) if parts[0] != "-" else 0
                    deletions = int(parts[1]) if parts[1] != "-" else 0
                    file_path = parts[2]

                    change_type = "modified"
                    if additions > 0 and deletions == 0:
                        change_type = "added"
                    elif additions == 0 and deletions > 0:
                        change_type = "deleted"

                    changes.append({
                        "type": "change",
                        "file": file_path,
                        "change_type": change_type,
                        "additions": additions,
                        "deletions": deletions,
                        "net_change": additions - deletions,
                        "base_ref": base_ref,
                        "head_ref": head_ref
                    })

            # Get detailed diff for changed files
            detailed_result = subprocess.run(
                ["git", "diff", "--unified=0", base_ref, head_ref],
                cwd=repo_path,
                capture_output=True,
                text=True
            )

            if detailed_result.returncode == 0:
                # Parse unified diff to get line numbers
                current_file = None
                for line in detailed_result.stdout.split("\n"):
                    if line.startswith("+++ b/"):
                        current_file = line[6:].strip()
                    elif line.startswith("@@") and current_file:
                        # Parse line numbers from @@ -old_start,old_count +new_start,new_count @@
                        parts = line.split("@@")
                        if len(parts) >= 2:
                            line_info = parts[1].strip()
                            if "+" in line_info:
                                new_line_info = line_info.split("+")[1].split()[0]
                                new_start = int(new_line_info.split(",")[0])
                                
                                # Find corresponding change entry
                                for change in changes:
                                    if change["file"] == current_file:
                                        change["line_start"] = new_start
                                        break

            return changes

        except FileNotFoundError:
            raise RuntimeError("Git is not installed or repository is not a git repo")
        except Exception as e:
            raise RuntimeError(f"ChangeAgent failed: {str(e)}")
