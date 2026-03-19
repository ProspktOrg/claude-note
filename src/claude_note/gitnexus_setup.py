"""GitNexus installation and setup helper.

Checks prerequisites (npm/npx), runs `gitnexus analyze`,
optionally generates skills, and verifies the index.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from . import gitnexus_client


def check_npm() -> bool:
    """Check if npm/npx is available."""
    return shutil.which("npx") is not None


def check_gitnexus() -> bool:
    """Check if gitnexus is installed (globally or via npx)."""
    try:
        result = subprocess.run(
            ["npx", "-y", "gitnexus@latest", "status"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def install_gitnexus_global() -> bool:
    """Install gitnexus globally via npm."""
    try:
        result = subprocess.run(
            ["npm", "install", "-g", "gitnexus"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def analyze_repo(repo_path: str = ".", force: bool = False, skills: bool = False) -> dict:
    """
    Index a repository with GitNexus.

    Args:
        repo_path: Path to the repository
        force: Force full re-index
        skills: Generate Leiden community skill files

    Returns:
        Dict with 'success', 'output', 'meta'
    """
    client = gitnexus_client.GitNexusClient(repo_path)
    success = client.analyze(path=None, force=force, skills=skills)

    result = {
        "success": success,
        "output": "",
        "meta": None,
    }

    if success:
        meta = client.read_repo_meta(repo_path)
        result["meta"] = meta

    return result


def get_status(repo_path: str = ".") -> dict:
    """
    Get GitNexus status for a repo.

    Returns dict with 'available', 'indexed', 'meta', 'repos'.
    """
    status = {
        "npm_available": check_npm(),
        "gitnexus_available": False,
        "indexed": False,
        "meta": None,
        "all_repos": [],
    }

    if not status["npm_available"]:
        return status

    client = gitnexus_client.GitNexusClient(repo_path)
    status["gitnexus_available"] = client.is_available()
    status["indexed"] = client.is_indexed()
    status["meta"] = client.read_repo_meta(repo_path)
    status["all_repos"] = [r.__dict__ for r in client.read_registry()]

    return status


def setup_full(
    repo_path: str = ".",
    install_global: bool = False,
    force_reindex: bool = False,
    generate_skills: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Full GitNexus setup: check prereqs, install, analyze, verify.

    Args:
        repo_path: Path to the repository to index
        install_global: Install gitnexus globally (vs npx)
        force_reindex: Force re-index even if up to date
        generate_skills: Generate Leiden community skill files
        verbose: Print progress

    Returns:
        Dict with step results
    """
    results = {
        "npm_ok": False,
        "gitnexus_ok": False,
        "analyzed": False,
        "skills_generated": False,
        "meta": None,
        "errors": [],
    }

    # Step 1: Check npm
    if not check_npm():
        results["errors"].append("npx not found. Install Node.js: https://nodejs.org/")
        return results
    results["npm_ok"] = True

    # Step 2: Install if requested
    if install_global:
        if verbose:
            print("Installing gitnexus globally...")
        if not install_gitnexus_global():
            results["errors"].append("Failed to install gitnexus globally")
            # Continue anyway -- npx will download on-demand

    results["gitnexus_ok"] = True  # npx will handle download

    # Step 3: Analyze
    if verbose:
        print(f"Indexing repository at {repo_path}...")
    analyze_result = analyze_repo(repo_path, force=force_reindex, skills=generate_skills)
    results["analyzed"] = analyze_result["success"]
    results["meta"] = analyze_result["meta"]

    if not analyze_result["success"]:
        results["errors"].append("gitnexus analyze failed")
        return results

    results["skills_generated"] = generate_skills

    return results
