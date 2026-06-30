import subprocess
from pathlib import Path


def get_git_revision(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return "unknown"

    revision = result.stdout.strip()
    if result.returncode != 0 or not revision:
        return "unknown"
    return revision
