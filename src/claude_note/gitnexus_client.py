"""GitNexus CLI client for AST-level code intelligence.

Wraps the real `gitnexus` CLI (https://github.com/abhigyanpatwari/GitNexus)
which outputs JSON from these commands:
- query: process-grouped hybrid search (BM25 + semantic)
- context: 360-degree symbol view (callers, callees, processes)
- impact: blast radius analysis with depth grouping and risk levels
- cypher: raw Cypher queries against the knowledge graph

Also reads the global registry at ~/.gitnexus/registry.json
and per-repo metadata at .gitnexus/meta.json.

Graceful fallback if gitnexus is not installed.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# =============================================================================
# Data models matching real GitNexus JSON output
# =============================================================================

@dataclass
class GNSymbol:
    """A code symbol from GitNexus."""
    uid: str = ""
    name: str = ""
    kind: str = ""         # Function, Class, Method, Interface, etc.
    file_path: str = ""
    start_line: int = 0
    end_line: int = 0
    module: str = ""       # Leiden community name
    content: str = ""      # Source code (only with --content flag)

    @classmethod
    def from_dict(cls, data: dict) -> "GNSymbol":
        return cls(
            uid=data.get("uid") or data.get("id", ""),
            name=data.get("name", ""),
            kind=data.get("kind") or data.get("type", ""),
            file_path=data.get("filePath") or data.get("file_path", ""),
            start_line=data.get("startLine") or data.get("start_line", 0),
            end_line=data.get("endLine") or data.get("end_line", 0),
            module=data.get("module", ""),
            content=data.get("content", ""),
        )


@dataclass
class GNProcess:
    """An execution flow traced by GitNexus."""
    id: str = ""
    summary: str = ""
    priority: float = 0.0
    symbol_count: int = 0
    process_type: str = ""  # cross_community, internal, etc.
    step_count: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "GNProcess":
        return cls(
            id=data.get("id", ""),
            summary=data.get("summary") or data.get("name", ""),
            priority=data.get("priority", 0.0),
            symbol_count=data.get("symbol_count", 0),
            process_type=data.get("process_type", ""),
            step_count=data.get("step_count", 0),
        )


@dataclass
class GNQueryResult:
    """Result from `gitnexus query`."""
    processes: list[GNProcess] = field(default_factory=list)
    symbols: list[GNSymbol] = field(default_factory=list)
    definitions: list[GNSymbol] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "GNQueryResult":
        return cls(
            processes=[GNProcess.from_dict(p) for p in data.get("processes", [])],
            symbols=[GNSymbol.from_dict(s) for s in data.get("process_symbols", [])],
            definitions=[GNSymbol.from_dict(d) for d in data.get("definitions", [])],
        )


@dataclass
class GNContextResult:
    """Result from `gitnexus context`."""
    status: str = ""  # found, ambiguous, not_found
    symbol: Optional[GNSymbol] = None
    incoming_calls: list[GNSymbol] = field(default_factory=list)
    outgoing_calls: list[GNSymbol] = field(default_factory=list)
    processes: list[dict] = field(default_factory=list)
    candidates: list[GNSymbol] = field(default_factory=list)  # if ambiguous

    @classmethod
    def from_dict(cls, data: dict) -> "GNContextResult":
        symbol = None
        if data.get("symbol"):
            symbol = GNSymbol.from_dict(data["symbol"])

        incoming = data.get("incoming", {})
        outgoing = data.get("outgoing", {})

        return cls(
            status=data.get("status", ""),
            symbol=symbol,
            incoming_calls=[GNSymbol.from_dict(c) for c in incoming.get("calls", [])],
            outgoing_calls=[GNSymbol.from_dict(c) for c in outgoing.get("calls", [])],
            processes=data.get("processes", []),
            candidates=[GNSymbol.from_dict(c) for c in data.get("candidates", [])],
        )


@dataclass
class GNImpactAffected:
    """A symbol affected by a change, with depth and confidence."""
    depth: int = 0
    uid: str = ""
    name: str = ""
    kind: str = ""
    file_path: str = ""
    relation_type: str = ""  # CALLS, IMPORTS, etc.
    confidence: float = 0.0

    @classmethod
    def from_dict(cls, data: dict) -> "GNImpactAffected":
        return cls(
            depth=data.get("depth", 0),
            uid=data.get("id", ""),
            name=data.get("name", ""),
            kind=data.get("type", ""),
            file_path=data.get("filePath", ""),
            relation_type=data.get("relationType", ""),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class GNImpactResult:
    """Result from `gitnexus impact`."""
    target: Optional[GNSymbol] = None
    direction: str = "upstream"
    impacted_count: int = 0
    risk: str = ""  # LOW, MEDIUM, HIGH, CRITICAL
    summary: dict = field(default_factory=dict)  # direct, processes_affected, modules_affected
    affected_processes: list[dict] = field(default_factory=list)
    affected_modules: list[dict] = field(default_factory=list)
    by_depth: dict[str, list[GNImpactAffected]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "GNImpactResult":
        target = None
        if data.get("target"):
            target = GNSymbol.from_dict(data["target"])

        by_depth = {}
        for depth_key, items in data.get("byDepth", {}).items():
            by_depth[depth_key] = [GNImpactAffected.from_dict(i) for i in items]

        return cls(
            target=target,
            direction=data.get("direction", "upstream"),
            impacted_count=data.get("impactedCount", 0),
            risk=data.get("risk", ""),
            summary=data.get("summary", {}),
            affected_processes=data.get("affected_processes", []),
            affected_modules=data.get("affected_modules", []),
            by_depth=by_depth,
        )


@dataclass
class GNRepoInfo:
    """Repository info from the global registry."""
    name: str = ""
    path: str = ""
    indexed_at: str = ""
    last_commit: str = ""
    files: int = 0
    nodes: int = 0
    edges: int = 0
    communities: int = 0
    processes: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "GNRepoInfo":
        stats = data.get("stats", {})
        return cls(
            name=data.get("name", ""),
            path=data.get("path", ""),
            indexed_at=data.get("indexedAt", ""),
            last_commit=data.get("lastCommit", ""),
            files=stats.get("files", 0),
            nodes=stats.get("nodes", 0),
            edges=stats.get("edges", 0),
            communities=stats.get("communities", 0),
            processes=stats.get("processes", 0),
        )


# =============================================================================
# Client
# =============================================================================

class GitNexusClient:
    """Client for the real GitNexus CLI."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = str(Path(repo_path).resolve())
        self._available: Optional[bool] = None

    def is_available(self) -> bool:
        """Check if gitnexus is installed."""
        if self._available is not None:
            return self._available

        try:
            result = subprocess.run(
                ["npx", "-y", "gitnexus@latest", "status"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=self.repo_path,
            )
            # status exits 0 even if not indexed, just check it runs
            self._available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            self._available = False

        return self._available

    def _run_json(self, args: list[str], timeout: int = 60) -> Optional[dict]:
        """
        Run a gitnexus CLI command that outputs JSON to stdout.

        GitNexus writes JSON via fs.writeSync(1, ...) to bypass LadybugDB
        stdout capture. We read from stdout.
        """
        if not self.is_available():
            return None

        try:
            cmd = ["npx", "-y", "gitnexus@latest"] + args
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.repo_path,
            )

            if result.returncode != 0:
                return None

            # JSON is on stdout
            output = result.stdout.strip()
            if not output:
                return None

            return json.loads(output)

        except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError, OSError):
            return None

    # ===== CLI commands that output JSON =====

    def query(
        self,
        search: str,
        repo: str = None,
        context: str = "",
        goal: str = "",
        limit: int = 5,
        include_content: bool = False,
    ) -> Optional[GNQueryResult]:
        """
        Search the knowledge graph for execution flows related to a concept.

        Returns processes, symbols, and definitions.
        """
        args = ["query", search, "--limit", str(limit)]
        if repo:
            args.extend(["--repo", repo])
        if context:
            args.extend(["--context", context])
        if goal:
            args.extend(["--goal", goal])
        if include_content:
            args.append("--content")

        data = self._run_json(args)
        if not data:
            return None
        return GNQueryResult.from_dict(data)

    def context(
        self,
        name: str,
        repo: str = None,
        uid: str = None,
        file_path: str = None,
        include_content: bool = False,
    ) -> Optional[GNContextResult]:
        """
        Get 360-degree view of a symbol: callers, callees, processes.
        """
        args = ["context", name]
        if repo:
            args.extend(["--repo", repo])
        if uid:
            args.extend(["--uid", uid])
        if file_path:
            args.extend(["--file", file_path])
        if include_content:
            args.append("--content")

        data = self._run_json(args)
        if not data:
            return None
        return GNContextResult.from_dict(data)

    def impact(
        self,
        target: str,
        repo: str = None,
        direction: str = "upstream",
        depth: int = 3,
        include_tests: bool = False,
    ) -> Optional[GNImpactResult]:
        """
        Blast radius analysis: what breaks if you change a symbol.

        Returns risk level, affected count, depth-grouped results.
        """
        args = ["impact", target, "--direction", direction, "--depth", str(depth)]
        if repo:
            args.extend(["--repo", repo])
        if include_tests:
            args.append("--include-tests")

        data = self._run_json(args)
        if not data:
            return None
        return GNImpactResult.from_dict(data)

    def cypher(self, query_str: str, repo: str = None) -> Optional[dict]:
        """
        Execute raw Cypher query against the knowledge graph.

        Returns {markdown: str, row_count: int}.
        """
        args = ["cypher", query_str]
        if repo:
            args.extend(["--repo", repo])
        return self._run_json(args)

    # ===== CLI commands with human-readable output =====

    def analyze(self, path: str = None, force: bool = False, skills: bool = False) -> bool:
        """
        Index a repository. Returns True if successful.
        """
        args = ["npx", "-y", "gitnexus@latest", "analyze"]
        if path:
            args.append(path)
        if force:
            args.append("--force")
        if skills:
            args.append("--skills")

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300,  # indexing can be slow
                cwd=self.repo_path,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return False

    # ===== Registry reading (machine-readable, no CLI needed) =====

    @staticmethod
    def read_registry() -> list[GNRepoInfo]:
        """
        Read the global GitNexus registry at ~/.gitnexus/registry.json.

        This is more reliable than parsing `gitnexus list` human output.
        """
        registry_path = Path.home() / ".gitnexus" / "registry.json"
        if not registry_path.exists():
            return []

        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [GNRepoInfo.from_dict(entry) for entry in data]
            return []
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def read_repo_meta(repo_path: str = ".") -> Optional[dict]:
        """Read per-repo metadata from .gitnexus/meta.json."""
        meta_path = Path(repo_path) / ".gitnexus" / "meta.json"
        if not meta_path.exists():
            return None

        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def is_indexed(self) -> bool:
        """Check if the current repo has been indexed."""
        return self.read_repo_meta(self.repo_path) is not None

    def get_communities_via_cypher(self, repo: str = None) -> list[dict]:
        """
        Get Leiden communities via Cypher query.

        Returns list of {name, member_count, ...} dicts.
        """
        result = self.cypher(
            "MATCH (c:Community) "
            "OPTIONAL MATCH (c)<-[:BELONGS_TO]-(s) "
            "RETURN c.name AS name, count(s) AS members "
            "ORDER BY members DESC",
            repo=repo,
        )
        if not result:
            return []

        # Parse markdown table output
        rows = []
        markdown = result.get("markdown", "")
        for line in markdown.split("\n"):
            line = line.strip()
            if not line or line.startswith("| ---") or line.startswith("| name"):
                continue
            if line.startswith("|"):
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    rows.append({"name": parts[0], "members": int(parts[1]) if parts[1].isdigit() else 0})
        return rows
