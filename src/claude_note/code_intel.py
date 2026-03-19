"""Code intelligence enrichment for engineering agent sessions.

Uses the real GitNexus CLI to enrich synthesis with:
- Symbol impact analysis (blast radius with risk levels and depth groups)
- Process/execution flow context
- Community/module membership
- Callers/callees via 360-degree context view
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config
from . import gitnexus_client


@dataclass
class CodeChange:
    """A code change with GitNexus intelligence context."""
    symbol: str
    file_path: str
    change_type: str = ""       # added, modified, deleted (from git diff)
    risk: str = ""              # LOW, MEDIUM, HIGH, CRITICAL (from gitnexus impact)
    impacted_count: int = 0     # total affected symbols
    direct_dependants: int = 0  # depth-1 impact count
    module: str = ""            # Leiden community name
    affected_processes: list[str] = field(default_factory=list)
    affected_modules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "file_path": self.file_path,
            "change_type": self.change_type,
            "risk": self.risk,
            "impacted_count": self.impacted_count,
            "direct_dependants": self.direct_dependants,
            "module": self.module,
            "affected_processes": self.affected_processes,
            "affected_modules": self.affected_modules,
        }


@dataclass
class CodeIntelContext:
    """Complete code intelligence context for a session."""
    changes: list[CodeChange] = field(default_factory=list)
    modules_affected: list[str] = field(default_factory=list)
    processes_affected: list[str] = field(default_factory=list)
    total_impacted: int = 0
    max_risk: str = ""  # highest risk among all changes
    available: bool = False
    indexed: bool = False  # whether repo is indexed in GitNexus

    def to_dict(self) -> dict:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "modules_affected": self.modules_affected,
            "processes_affected": self.processes_affected,
            "total_impacted": self.total_impacted,
            "max_risk": self.max_risk,
            "available": self.available,
            "indexed": self.indexed,
        }


# Risk level ordering for max computation
_RISK_ORDER = {"": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _get_changed_files(repo_path: str, ref: str = "HEAD~1") -> list[dict]:
    """
    Get changed files from git diff.

    Returns list of {file_path, change_type} dicts.
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", ref],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=repo_path,
        )
        if result.returncode != 0:
            return []

        changes = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                change_type = {"A": "added", "M": "modified", "D": "deleted"}.get(status[0], "modified")
                changes.append({"file_path": path, "change_type": change_type})
        return changes
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []


def _extract_symbols_from_file(client: gitnexus_client.GitNexusClient, file_path: str) -> list[str]:
    """Find key symbols in a file via GitNexus query."""
    result = client.query(file_path, limit=3)
    if not result or not result.symbols:
        return []
    return [s.name for s in result.symbols if s.name]


class CodeIntelEnricher:
    """Enriches session context with code intelligence from GitNexus CLI."""

    def __init__(self, repo_path: str = "."):
        self.client = gitnexus_client.GitNexusClient(repo_path)
        self.repo_path = repo_path

    def is_available(self) -> bool:
        """Check if GitNexus is installed and repo is indexed."""
        return self.client.is_available() and self.client.is_indexed()

    def enrich_session(self, ref: str = "HEAD~1") -> CodeIntelContext:
        """
        Gather code intelligence for current session changes.

        Strategy: git diff → changed files → gitnexus impact per key symbol.
        (detect_changes is MCP-only, so we approximate via git diff + impact)
        """
        ctx = CodeIntelContext()

        if not self.client.is_available():
            return ctx
        ctx.available = True

        if not self.client.is_indexed():
            return ctx
        ctx.indexed = True

        # Get changed files from git
        changed_files = _get_changed_files(self.repo_path, ref)
        if not changed_files:
            return ctx

        all_modules = set()
        all_processes = set()
        max_risk = ""

        for file_info in changed_files[:15]:  # Cap at 15 files
            file_path = file_info["file_path"]
            change_type = file_info["change_type"]

            # Find symbols in this file
            symbols = _extract_symbols_from_file(self.client, file_path)
            if not symbols:
                # Still record the file change without symbol-level detail
                ctx.changes.append(CodeChange(
                    symbol=Path(file_path).stem,
                    file_path=file_path,
                    change_type=change_type,
                ))
                continue

            # Run impact analysis on the first (most relevant) symbol
            symbol_name = symbols[0]
            impact = self.client.impact(symbol_name)

            if impact:
                # Extract module from context
                module = ""
                sym_context = self.client.context(symbol_name)
                if sym_context and sym_context.symbol:
                    module = sym_context.symbol.module

                proc_names = [p.get("name", "") for p in impact.affected_processes if p.get("name")]
                mod_names = [m.get("name", "") for m in impact.affected_modules if m.get("name")]

                change = CodeChange(
                    symbol=symbol_name,
                    file_path=file_path,
                    change_type=change_type,
                    risk=impact.risk,
                    impacted_count=impact.impacted_count,
                    direct_dependants=impact.summary.get("direct", 0),
                    module=module,
                    affected_processes=proc_names,
                    affected_modules=mod_names,
                )
                ctx.changes.append(change)
                ctx.total_impacted += impact.impacted_count

                all_modules.update(mod_names)
                all_processes.update(proc_names)
                if module:
                    all_modules.add(module)

                if _RISK_ORDER.get(impact.risk, 0) > _RISK_ORDER.get(max_risk, 0):
                    max_risk = impact.risk
            else:
                ctx.changes.append(CodeChange(
                    symbol=symbol_name,
                    file_path=file_path,
                    change_type=change_type,
                ))

        ctx.modules_affected = sorted(all_modules)
        ctx.processes_affected = sorted(all_processes)
        ctx.max_risk = max_risk
        return ctx

    def format_for_prompt(self, ctx: CodeIntelContext) -> str:
        """Format code intelligence as a section for synthesis prompts."""
        if not ctx.available:
            return "(Code intelligence not available -- gitnexus not installed)"

        if not ctx.indexed:
            return "(Repository not indexed -- run: gitnexus analyze)"

        if not ctx.changes:
            return "(No code changes detected)"

        lines = []

        # Summary header
        risk_str = f", overall risk: **{ctx.max_risk}**" if ctx.max_risk else ""
        lines.append(
            f"**{len(ctx.changes)} files changed**, "
            f"{ctx.total_impacted} symbols affected{risk_str}"
        )
        lines.append("")

        # Per-change details
        for change in ctx.changes:
            status = {"added": "+", "modified": "~", "deleted": "-"}.get(change.change_type, "?")
            risk_badge = f" [{change.risk}]" if change.risk else ""
            lines.append(f"  {status} `{change.symbol}` ({change.file_path}){risk_badge}")

            details = []
            if change.impacted_count:
                details.append(f"{change.impacted_count} affected ({change.direct_dependants} direct)")
            if change.module:
                details.append(f"module: {change.module}")
            if details:
                lines.append(f"    {', '.join(details)}")

            if change.affected_processes:
                lines.append(f"    Processes: {', '.join(change.affected_processes[:5])}")

        # Aggregate
        if ctx.modules_affected:
            lines.append("")
            lines.append(f"Modules affected: {', '.join(ctx.modules_affected)}")

        if ctx.processes_affected:
            lines.append(f"Execution flows affected: {', '.join(ctx.processes_affected[:10])}")

        return "\n".join(lines)
