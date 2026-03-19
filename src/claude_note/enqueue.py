#!/usr/bin/env python3
"""
Fast hook handler for claude-note.

Reads hook event from stdin and appends to queue.
Must be FAST - exits immediately, even on errors.

On the first UserPromptSubmit of a session, triggers context
injection in the background (non-blocking).
"""

import json
import os
import subprocess
import sys

from . import models
from . import queue_manager


def _maybe_inject_context(session_id: str, agent_id: str) -> None:
    """
    Inject agent context into CLAUDE.md on first event of a session.

    Uses a marker file to ensure this only runs once per session.
    Runs claude-note context --inject in a detached subprocess so
    it doesn't block the hook.
    """
    try:
        from . import config
        if not config.AGENT_ENABLED:
            return

        marker_dir = config.STATE_DIR / "context_injected"
        marker_dir.mkdir(parents=True, exist_ok=True)
        marker = marker_dir / f"{session_id}.marker"

        if marker.exists():
            return  # Already injected for this session

        # Create marker immediately (before subprocess) to avoid races
        marker.write_text(session_id, encoding="utf-8")

        # Build command
        cmd = [sys.executable, "-m", "claude_note.cli", "context", "--inject"]
        if agent_id:
            cmd.extend(["--agent", agent_id])

        # Fire and forget -- detached subprocess, don't wait
        # Inherit env so CLAUDE_NOTE_VAULT_ROOT etc. are available
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass  # Never block the hook


def main() -> int:
    """Main entry point for enqueue command."""
    try:
        # Read JSON from stdin
        raw_input = sys.stdin.read()
        if not raw_input.strip():
            # No input is fine, just exit
            return 0

        hook_data = json.loads(raw_input)

        # Read agent ID: env var (Paperclip) → env var (manual) → config.toml
        agent_id = os.environ.get("PAPERCLIP_AGENT_ID", "")
        if not agent_id:
            agent_id = os.environ.get("CLAUDE_NOTE_AGENT_ID", "")
        if not agent_id:
            try:
                from . import config as _cfg
                if _cfg.AGENT_ENABLED and _cfg.AGENT_ID and _cfg.AGENT_ID != "default":
                    agent_id = _cfg.AGENT_ID
            except Exception:
                pass

        # Create event and enqueue
        event = models.QueuedEvent.from_hook_input(hook_data, agent_id=agent_id)
        queue_manager.enqueue_event(event)

        # On first event of a session, inject context in the background
        event_name = hook_data.get("hook_event_name", "")
        if event_name == "UserPromptSubmit":
            session_id = hook_data.get("session_id", "")
            if session_id:
                _maybe_inject_context(session_id, agent_id)

        return 0

    except json.JSONDecodeError as e:
        # Log to stderr but don't fail the hook
        print(f"claude-note: JSON decode error: {e}", file=sys.stderr)
        return 0

    except Exception as e:
        # Log to stderr but don't fail the hook
        print(f"claude-note: Error: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
