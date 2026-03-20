# Claude Note

Automatic knowledge extraction from Claude Code sessions into your Obsidian vault.

Claude Note runs as a background service, capturing your Claude Code sessions and synthesizing key learnings, decisions, and questions into structured notes. In v2, it can serve as a **company brain** for multi-agent teams -- each agent gets role-scoped context, domain briefings, and a shared knowledge graph.

## How It Works

There are two flows: **context loading** (session start) and **knowledge capture** (session end).

### Session Start: Loading Context

When a session starts, the `SessionStart` hook fires once. `claude-note context` prints vault knowledge to stdout, and Claude Code injects it directly into the conversation:

```
New Claude Code session starts
        |
        v
SessionStart hook fires:
        |
        +-- claude-note context           (runs ONCE, ~200ms)
                |
                +-- Resolve agent ID        PAPERCLIP_AGENT_ID / config.toml / env var
                +-- Check briefing          Stale? --> regenerate via Claude CLI
                +-- Score vault notes       6-component scoring
                +-- Budget-constrain        High (full) / Mid (preview) / Low (link)
                +-- Print to stdout
                        |
                        v
                Claude Code captures stdout --> context in conversation
```

**The 6 scoring components** (how notes are ranked per agent):

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Tag match | 0.30 | Overlap with agent's owned tags |
| Department | 0.15 | Is the note in the agent's primary/secondary folders? |
| Recency | 0.20 | Exponential decay, 14-day half-life |
| Mycelium | 0.20 | Spreading activation from knowledge graph |
| Semantic | 0.10 | Vector similarity via qmd (if installed) |
| Hub | 0.05 | Is it in `_hub/` (cross-functional)? |

### Session End: Capturing Knowledge

When you end a session (Ctrl+C, `/exit`, close terminal), claude-note synthesizes what happened:

```
Stop hook fires
        |
        v
  claude-note enqueue --> queue/.jsonl
        |
        v
  Worker daemon (polls every 2s)
        |
        |  Session ended? --> process immediately (skip debounce)
        v
  +------------------+
  | 1. Write session |  claude-session-YYYY-MM-DD-ID.md (timeline)
  |    note          |
  |                  |
  | 2. Synthesize    |  Claude CLI reads transcript + vault context
  |    (Claude CLI)  |  + agent briefing + GitNexus code intel
  |                  |  + Mycelium graph activation
  |                  |
  | 3. Route         |  Own dept --> department folder
  |    knowledge     |  Decisions --> _hub/decisions-log.md
  |                  |  Ambiguous --> agent inbox (deferred)
  |                  |  Cross-dept --> mark other briefings stale
  |                  |
  | 4. Update graph  |  Add synthesis edges, reinforce paths
  +------------------+
        |
        v
  Vault updated with new knowledge
```

**What gets extracted** (the KnowledgePack):
- **Concepts** -- durable learnings with 2-4 sentence summaries
- **Decisions** -- what was decided and why
- **Open Questions** -- unresolved items for follow-up
- **How-tos** -- step-by-step procedures discovered
- **Note Ops** -- create/update/append operations on vault notes

## Features

- **Session Logging** -- captures every Claude Code session as a markdown timeline
- **Knowledge Synthesis** -- Claude extracts concepts, decisions, how-tos, and open questions
- **Smart Routing** -- routes knowledge to inbox, updates existing notes, or creates new ones
- **Open Questions Tracking** -- detects and promotes questions from sessions
- **Vault Integration** -- understands your existing notes for better linking context
- **Cross-Platform** -- works on macOS, Linux, and Windows
- **Pure stdlib** -- no Python dependencies (only requires Claude CLI for synthesis)

### v2: Company Brain

- **Multi-Agent Support** -- role-based agents (CEO, CTO, CMO, etc.) with department-scoped context
- **Domain Briefings** -- auto-generated briefings per agent, refreshed when stale
- **Context Injection** -- injects relevant vault knowledge into CLAUDE.md before sessions
- **Mycelium Knowledge Graph** -- bio-inspired graph with FSRS decay, spreading activation, and self-healing
- **GitNexus Code Intelligence** -- AST-level blast radius analysis, Leiden community detection
- **Decision Propagation** -- CEO decisions automatically reach CMO/CTO briefings
- **Works with or without Paperclip** -- set agent ID via env var, config file, or Paperclip

## Requirements

- Python 3.11+
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (for synthesis)
- An Obsidian vault or any markdown notes folder
- Optional: [Node.js](https://nodejs.org/) (for GitNexus code intelligence)

## Quick Start

### Linux / macOS / Git Bash on Windows

```bash
git clone https://github.com/artemiin/claude-note.git
cd claude-note
./install.sh
```

### Windows (PowerShell)

```powershell
git clone https://github.com/artemiin/claude-note.git
cd claude-note
.\install.ps1
```

The installer will:
1. Check dependencies (uv, git, Claude CLI)
2. Ask for your vault path
3. Install claude-note via `uv tool install`
4. Write config to `~/.config/claude-note/config.toml`
5. Initialize vault structure
6. Set up the background worker (systemd/launchd/Task Scheduler)
7. Optionally set up the classifier timer (every 15 min)
8. Optionally index your repo with GitNexus
9. Install Claude Code hooks automatically
10. Install skills

## Commands

```bash
# Core
claude-note status          # Show queue, sessions, vault index status
claude-note drain           # Process all pending sessions now (skip debounce)
claude-note worker          # Start background worker (foreground mode: -f)
claude-note enqueue         # Hook handler (reads JSON from stdin)

# Vault
claude-note index           # Rebuild vault note index
claude-note clean           # Cleanup: dedupe inbox, compress timelines, prune graph
claude-note resynth <id>    # Re-synthesize a specific session
claude-note ingest <file>   # Ingest PDF/DOCX into literature notes

# v2: Multi-Agent
claude-note agents init     # Create agent profiles + vault department structure
claude-note agents list     # List all registered agents
claude-note agents show <id># Show agent profile JSON
claude-note context --inject# Inject agent context into vault CLAUDE.md
claude-note context --remove# Remove injected context
claude-note briefing show <id>      # Show agent briefing
claude-note briefing regenerate <id># Regenerate agent briefing via Claude CLI
claude-note briefing status <id>    # Check briefing staleness

# v2: Knowledge Graph
claude-note graph sync      # Sync vault notes to Mycelium graph
claude-note graph stats     # Show node/edge counts
claude-note graph hubs      # Find knowledge hub nodes (betweenness centrality)
claude-note graph decay     # Apply FSRS temporal decay to all nodes

# v2: Classifier
claude-note classify        # Process agent inboxes, route to departments
claude-note migrate         # Plan/execute flat-to-structured vault migration

# Updates
claude-note update          # Check for and apply updates
```

## Configuration

Config file: `~/.config/claude-note/config.toml`

```toml
vault_root = "/path/to/your/vault"

[synthesis]
mode = "route"                    # log | inbox | route
model = "claude-sonnet-4-5-20250929"

[agent]
enabled = true                    # Enable multi-agent features
id = "solo"                       # Agent ID (when PAPERCLIP_AGENT_ID not set)
                                  # Options: solo, ceo, cmo, cto, head-of-sales

[mycelium]
enabled = true                    # Enable knowledge graph
decay_factor = 0.6                # Spreading activation decay per hop
max_hops = 3                      # Max propagation depth

[gitnexus]
enabled = true                    # Enable code intelligence

[qmd]
enabled = false                   # Enable qmd semantic search
```

### Agent ID Resolution

The agent identity is resolved in this order:
1. `PAPERCLIP_AGENT_ID` env var (set by Paperclip for multi-agent teams)
2. `CLAUDE_NOTE_AGENT_ID` env var (manual override)
3. `[agent] id` in config.toml (standalone setup)
4. `"default"` fallback (single-user, no scoping)

This means claude-note works identically whether you're using Paperclip, running standalone, or just want basic session logging.

### Claude Code Hooks

The installer writes five hooks to `~/.claude/settings.json`:

| Hook | Command | Purpose |
|------|---------|---------|
| **SessionStart** | `claude-note context` | Inject vault context once at session start |
| **PostToolUse** | `claude-note enqueue` | Capture every tool use |
| **UserPromptSubmit** | `claude-note enqueue` | Capture every prompt |
| **PostCompact** | `claude-note context` | Re-inject vault context after compaction |
| **Stop** | `claude-note enqueue` | Capture session end, trigger synthesis |

**How context injection works:** `SessionStart` fires once when a new session begins. `claude-note context` prints scored vault notes, the agent briefing, and recent decisions to stdout. Claude Code captures this stdout and injects it directly into the conversation context -- no file modification needed. `PostCompact` re-injects the same context after compaction so long sessions don't lose vault knowledge.

If you need to install hooks manually:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [
      { "type": "command", "command": "claude-note context", "timeout": 5000 }
    ]}],
    "PostToolUse": [{ "hooks": [
      { "type": "command", "command": "claude-note enqueue", "timeout": 5000 }
    ]}],
    "UserPromptSubmit": [{ "hooks": [
      { "type": "command", "command": "claude-note enqueue", "timeout": 5000 }
    ]}],
    "PostCompact": [{ "hooks": [
      { "type": "command", "command": "claude-note context", "timeout": 5000 }
    ]}],
    "Stop": [{ "hooks": [
      { "type": "command", "command": "claude-note enqueue", "timeout": 5000 }
    ]}]
  }
}
```

## Vault Structure

### v1 (default, backward-compatible)

```
your-vault/
├── .claude-note/               # Internal state
│   ├── queue/                  # JSONL event queues
│   ├── state/                  # Session state
│   └── logs/                   # Worker logs
├── claude-note-inbox.md        # Synthesized knowledge
├── open-questions.md           # Question tracker
└── claude-session-*.md         # Session logs
```

### v2 (multi-agent, after `claude-note agents init`)

```
your-vault/
├── .claude-note/               # Internal state
│   ├── queue/                  # JSONL event queues
│   ├── state/                  # Session state
│   ├── logs/                   # Worker logs
│   ├── graph/                  # Mycelium knowledge graph (nodes.json, edges.json)
│   └── agents/                 # Agent registry (ceo.json, cmo.json, ...)
│
├── _hub/                       # Cross-functional (all agents read)
│   ├── company-brain.md        # Master MOC
│   ├── strategy.md             # Company strategy
│   ├── decisions-log.md        # All decisions chronologically
│   └── ...
│
├── _agents/                    # Per-agent config + briefings
│   ├── ceo/
│   │   ├── CLAUDE.md           # Agent-specific vault navigation
│   │   ├── briefing.md         # Auto-generated domain briefing
│   │   └── inbox.md            # Unprocessed synthesis output
│   ├── cmo/
│   ├── cto/
│   └── ...
│
├── executive/                  # Department folders
├── marketing/
│   ├── campaigns/
│   ├── brand/
│   └── _moc-marketing.md      # Auto-maintained Map of Content
├── sales/
├── engineering/
│   └── architecture/           # GitNexus community notes land here
├── product/
├── operations/
│
├── journal/                    # Session logs (by date/week/quarter)
│   └── 2026/2026-Q1/2026-W12/
│       └── 2026-03-19-cto-session-abc12345.md
│
└── literature/                 # Ingested external research
```

## GitNexus Code Intelligence

[GitNexus](https://github.com/abhigyanpatwari/GitNexus) provides AST-level code understanding via Leiden community detection and execution flow tracing.

```bash
# Index your repository (one-time)
npx gitnexus analyze --skills

# Or install globally
npm install -g gitnexus
gitnexus analyze --skills
```

When enabled (`[gitnexus] enabled = true`), the synthesis prompt gets enriched with:
- Which symbols were modified and their blast radius
- Risk levels (LOW/MEDIUM/HIGH/CRITICAL)
- Affected execution flows and modules
- Leiden community membership

Architecture notes are auto-generated in `engineering/architecture/` from detected code communities.

**CLI tools used** (all output JSON):
- `gitnexus query <search>` -- find execution flows by concept
- `gitnexus context <symbol>` -- 360-degree symbol view (callers, callees, processes)
- `gitnexus impact <symbol>` -- blast radius with depth grouping
- `gitnexus cypher <query>` -- raw graph queries

## Mycelium Knowledge Graph

A bio-inspired knowledge graph stored at `.claude-note/graph/`. Implements six mechanisms:

1. **FSRS Temporal Decay** -- notes you haven't accessed lose retrieval strength over time
2. **Adaptive Path Reinforcement** -- frequently traversed connections get stronger
3. **Self-Healing** -- when a node is pruned, bypass edges are created to maintain connectivity
4. **Frontier Shielding** -- newly created notes in active departments are protected from pruning
5. **Flow Scoring** -- identifies knowledge hub nodes via betweenness centrality
6. **Spreading Activation** -- finds relevant notes by propagating activation from seed nodes

The graph feeds into the relevance scorer (20% weight) to help each agent find the most relevant notes for their context.

## Service Management

### macOS (launchd)

```bash
launchctl list | grep claude-note
launchctl stop com.claude-note.worker
launchctl start com.claude-note.worker
```

### Linux (systemd)

```bash
systemctl --user status claude-note
systemctl --user stop claude-note
systemctl --user start claude-note
```

### Windows

```powershell
# If Task Scheduler was set up (requires admin):
schtasks.exe /Query /TN ClaudeNoteWorker
schtasks.exe /End /TN ClaudeNoteWorker
schtasks.exe /Run /TN ClaudeNoteWorker

# Otherwise, run manually:
claude-note worker --foreground
```

## Architecture

```
enqueue.py ──► queue_manager.py ──► worker.py ──► synthesizer.py ──► note_router.py
                                        │               │                   │
                                        │         (Claude CLI)        ┌─────┴──────┐
                                        │               │             │            │
                                   note_writer.py  knowledge_pack.py  │  briefing_ │
                                        │               │             │  updater   │
                                        ▼               ▼             ▼            ▼
                                   session note    KnowledgePack   vault notes  decisions-log
```

### Key Modules

| Module | Purpose |
|--------|---------|
| `enqueue.py` | Hook handler -- stdin JSON to queue file |
| `worker.py` | Background daemon -- poll, debounce, synthesize |
| `synthesizer.py` | Claude CLI calls for knowledge extraction |
| `note_router.py` | Route knowledge to vault (inbox/create/update) |
| `agent_config.py` | Agent profiles, registry, ID resolution |
| `vault_zones.py` | Department folder management |
| `context_retriever.py` | CLAUDE.md context injection |
| `relevance_scorer.py` | 6-component note scoring per agent |
| `briefing_generator.py` | Auto-generate domain briefings |
| `classifier_job.py` | Periodic inbox processing and routing |
| `gitnexus_client.py` | GitNexus CLI wrapper (query, context, impact) |
| `code_intel.py` | Code intelligence enrichment for synthesis |
| `mycelium/` | Knowledge graph (FSRS, spreading activation) |

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting Started](docs/getting-started.md) | Step-by-step installation |
| [Configuration](docs/configuration.md) | Complete config reference |
| [Commands](docs/commands.md) | All CLI commands |
| [Synthesis Modes](docs/synthesis-modes.md) | log vs inbox vs route |
| [Hook Setup](docs/hook-setup.md) | Claude Code integration |
| [Service Setup](docs/service-setup.md) | launchd/systemd/Task Scheduler |
| [QMD Integration](docs/qmd-integration.md) | Semantic search setup |
| [Document Ingestion](docs/document-ingestion.md) | Importing papers and docs |
| [Architecture](docs/architecture.md) | How it works internally |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and fixes |

## License

MIT
