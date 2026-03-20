#!/usr/bin/env python3
"""
Fast hook handler for claude-note.

Reads hook event from stdin and appends to queue.
Must be FAST - exits immediately, even on errors.
"""

import json
import os
import sys

from . import models
from . import queue_manager


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
