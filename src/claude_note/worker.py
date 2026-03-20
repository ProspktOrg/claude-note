#!/usr/bin/env python3
"""
Background worker daemon for claude-note.

Polls the queue and processes sessions when debounce expires.
"""

import argparse
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

from . import config
from . import models
from . import queue_manager
from . import session_tracker
from . import note_writer
from . import open_questions
from . import synthesizer
from . import note_router
from . import vault_indexer
from . import version_checker


# Global flag for graceful shutdown
_shutdown = False


def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configure logging for the worker."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_file = config.LOGS_DIR / f"worker-{datetime.utcnow().strftime('%Y-%m-%d')}.log"

    level = logging.DEBUG if verbose else logging.INFO

    # Configure root logger
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler() if verbose else logging.NullHandler(),
        ],
    )

    return logging.getLogger("claude-note")


def handle_signal(signum, frame):
    """Handle shutdown signals gracefully."""
    global _shutdown
    _shutdown = True



def compact_session(state: models.SessionState, logger: logging.Logger) -> bool:
    """
    Stage 1: Compact a session into a digest (like /compact).

    Reads the transcript and produces a concise summary appended to
    the session note. Does NOT extract knowledge or route to vault --
    that's the daily synthesis job (Stage 2).

    Returns True if digest was written.
    """
    if config.SYNTH_MODE == "log":
        return False

    if not state.transcript_path:
        logger.debug(f"Session {state.session_id[:8]}: no transcript, skipping compact")
        return False

    try:
        from . import transcript_reader

        transcript = transcript_reader.read_transcript(state.transcript_path)
        if not transcript.user_prompts:
            return False

        # Build a compact prompt -- just summarize, don't extract knowledge
        user_prompts = "\n".join(
            f"{i}. {p[:300]}" for i, p in enumerate(transcript.user_prompts[:20], 1)
        )
        files_list = ", ".join(transcript.files_touched[:20])

        prompt = f"""Summarize this Claude Code session in a concise digest.

## Session
Working directory: {state.cwd or "unknown"}
Date: {state.first_event_ts[:10] if state.first_event_ts else "unknown"}

## User Prompts
{user_prompts}

## Files Touched
{files_list}

## Errors
{chr(10).join(transcript.errors[:5]) if transcript.errors else "(None)"}

## Output Format
Write a concise session digest with these sections:
- **What**: 1-2 sentences on what was accomplished
- **Key Changes**: Bullet list of significant changes/decisions (max 5)
- **Open Threads**: Anything left unresolved (max 3)
- **Files Modified**: Key files that were changed

Keep it SHORT. This digest will be processed later by a daily synthesis job.
Output plain markdown only, no JSON, no code blocks."""

        env = os.environ.copy()
        env["CLAUDE_CODE_HOOKS_ENABLED"] = "false"

        result = subprocess.run(
            ["claude", "-p", prompt, "--model", config.SYNTH_MODEL],
            capture_output=True,
            text=True,
            env=env,
            timeout=config.SYNTH_TIMEOUT,
        )

        if result.returncode != 0:
            logger.warning(f"Session {state.session_id[:8]}: compact failed: {result.stderr[:200]}")
            return False

        digest = result.stdout.strip()
        if not digest:
            return False

        # Write digest to the session note's Summary section
        update_session_summary_with_digest(state, digest, logger)
        logger.info(f"Compacted session {state.session_id[:8]}")
        return True

    except Exception as e:
        logger.error(f"Compact failed for session {state.session_id[:8]}: {e}")
        return False


def update_session_summary_with_digest(state: models.SessionState, digest: str, logger: logging.Logger) -> bool:
    """Replace the Summary placeholder in the session note with the digest."""
    try:
        note_path = note_writer.get_note_path(state)
        if not note_path.exists():
            return False

        content = note_path.read_text(encoding="utf-8")

        placeholder = "(Updated on Stop/SessionEnd with session highlights)"
        if placeholder in content:
            new_content = content.replace(placeholder, digest)
        else:
            # Try regex replace of Summary section
            pattern = r"(## Summary\n\n).*?(\n\n## )"
            match = re.search(pattern, content, re.DOTALL)
            if match:
                new_content = content[:match.start()] + match.group(1) + digest + match.group(2) + content[match.end():]
            else:
                return False

        temp_path = note_path.with_suffix(".tmp")
        temp_path.write_text(new_content, encoding="utf-8")
        temp_path.replace(note_path)
        return True

    except Exception as e:
        logger.error(f"Failed to write digest: {e}")
        return False


def process_session(session_id: str, events: list, logger: logging.Logger) -> bool:
    """
    Process a single session.

    Returns True if note was written, False otherwise.
    """
    with session_tracker.session_lock(session_id) as acquired:
        if not acquired:
            logger.debug(f"Could not acquire lock for session {session_id[:8]}")
            return False

        try:
            # Update session state from events
            state = session_tracker.update_session_from_events(session_id, events)

            # Skip sessions without user prompts
            has_user_prompt = any(
                e.get("event") == "UserPromptSubmit"
                for e in state.events
            )
            if not has_user_prompt:
                logger.debug(f"Session {session_id[:8]}: no user prompt, skipping")
                return False

            # Skip subagent sessions -- their work is in the parent transcript.
            # Hook data includes is_subagent=true and parent_session_id for subagents.
            is_subagent = any(
                e.data.get("is_subagent", False)
                for e in events
            )
            if is_subagent:
                logger.debug(f"Session {session_id[:8]}: subagent, skipping")
                return False

            # Check if we should write now
            immediate = session_tracker.should_flush_immediately(events)
            debounce_ok = state.should_write(config.DEBOUNCE_SECONDS)

            # Skip if already written after last event (even for immediate events)
            already_written = session_tracker.is_session_written(state)
            if already_written:
                logger.debug(f"Session {session_id[:8]}: already written, skipping")
                return False

            if not immediate and not debounce_ok:
                # Save state but don't write note yet
                session_tracker.save_session_state(state)
                logger.debug(f"Session {session_id[:8]}: debounce not ready")
                return False

            # Write the note
            note_path = note_writer.update_session_note(state)
            logger.info(f"Wrote note: {note_path.name}")

            # Promote questions on Stop/SessionEnd
            if immediate:
                count = open_questions.promote_session_questions(state)
                if count > 0:
                    logger.info(f"Promoted {count} questions to open-questions.md")

                # Compact session into digest (Stage 1)
                # Knowledge extraction happens in daily synthesis (Stage 2)
                compact_session(state, logger)

            # Mark as written (update state object directly, then save once)
            state.last_write_ts = datetime.utcnow().isoformat() + "Z"
            session_tracker.save_session_state(state)

            return True

        except Exception as e:
            logger.error(f"Error processing session {session_id[:8]}: {e}")
            return False


def poll_once(logger: logging.Logger) -> int:
    """
    Process all pending sessions once.

    Returns number of notes written.
    """
    # Group events by session
    sessions: dict[str, list] = {}
    for event in queue_manager.read_all_events():
        if event.session_id not in sessions:
            sessions[event.session_id] = []
        sessions[event.session_id].append(event)

    notes_written = 0
    for session_id, events in sessions.items():
        if process_session(session_id, events, logger):
            notes_written += 1

    return notes_written


def run_worker(foreground: bool = False, verbose: bool = False) -> int:
    """
    Run the worker daemon.

    Args:
        foreground: If True, log to stdout as well
        verbose: If True, enable debug logging
    """
    logger = setup_logging(verbose=verbose or foreground)
    logger.info("Worker starting")

    # Check for updates (non-blocking)
    try:
        version_checker.check_for_update(logger)
    except Exception:
        pass  # Never let version check break worker

    # Set up signal handlers
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    # Main poll loop
    while not _shutdown:
        try:
            notes_written = poll_once(logger)
            if notes_written > 0:
                logger.debug(f"Poll cycle: wrote {notes_written} notes")

            # Clean up old queue files periodically (once per poll)
            queue_manager.cleanup_old_queue_files(keep_days=7)

        except Exception as e:
            logger.error(f"Error in poll cycle: {e}")

        # Sleep until next poll
        time.sleep(config.POLL_INTERVAL)

    logger.info("Worker shutting down")
    return 0


def main() -> int:
    """Main entry point for worker command."""
    parser = argparse.ArgumentParser(description="Claude Note background worker")
    parser.add_argument(
        "--foreground", "-f", action="store_true", help="Run in foreground with output"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    args = parser.parse_args()

    return run_worker(foreground=args.foreground, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
