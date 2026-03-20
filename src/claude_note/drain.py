#!/usr/bin/env python3
"""
One-shot queue processing for claude-note.

Processes all pending sessions immediately, ignoring debounce.
Useful for testing and manual processing.
"""

import sys

from . import config
from . import queue_manager
from . import session_tracker
from . import note_writer
from . import open_questions
from . import synthesizer
from . import note_router
from . import vault_indexer


def run_synthesis_for_drain(state) -> bool:
    """Run synthesis for a session during drain."""
    if config.SYNTH_MODE == "log":
        return False

    if not state.transcript_path:
        return False

    try:
        vault_index = vault_indexer.get_index()
        pack = synthesizer.synthesize_from_state(state, vault_index)

        if pack is None or pack.is_empty():
            return False

        results = note_router.apply_note_ops(pack, mode=config.SYNTH_MODE)

        if results["inbox_updated"]:
            print(f"  Synthesized: {len(pack.concepts)} concepts, {len(pack.decisions)} decisions")

        return True

    except Exception as e:
        print(f"  Synthesis error: {e}")
        return False


def drain_all() -> tuple:
    """
    Process all pending sessions immediately.

    Returns (sessions_processed, notes_written).
    """
    # Group events by session
    sessions: dict[str, list] = {}
    for event in queue_manager.read_all_events():
        if event.session_id not in sessions:
            sessions[event.session_id] = []
        sessions[event.session_id].append(event)

    sessions_processed = 0
    notes_written = 0

    for session_id, events in sessions.items():
        with session_tracker.session_lock(session_id) as acquired:
            if not acquired:
                print(f"Could not acquire lock for session {session_id[:8]}")
                continue

            try:
                # Update session state from events
                state = session_tracker.update_session_from_events(session_id, events)

                # Check if we have any new events to process
                if not state.events:
                    continue

                # Skip sessions without user prompts (same as worker.py)
                has_user_prompt = any(
                    e.get("event") == "UserPromptSubmit"
                    for e in state.events
                )
                if not has_user_prompt:
                    continue

                # Skip subagent sessions -- parent transcript has their work
                is_subagent = any(
                    e.data.get("is_subagent", False)
                    for e in events
                )
                if is_subagent:
                    continue

                # Skip already-written sessions (same as worker.py)
                if session_tracker.is_session_written(state):
                    continue

                sessions_processed += 1

                # Write the note (ignore debounce in drain mode)
                note_path = note_writer.update_session_note(state)
                print(f"Wrote: {note_path.name}")
                notes_written += 1

                # Promote questions
                count = open_questions.promote_session_questions(state)
                if count > 0:
                    print(f"  Promoted {count} questions")

                # Run synthesis (if enabled)
                run_synthesis_for_drain(state)

                # Mark as written
                session_tracker.mark_session_written(session_id)
                session_tracker.save_session_state(state)

            except Exception as e:
                print(f"Error processing session {session_id[:8]}: {e}")

    return sessions_processed, notes_written


def main() -> int:
    """Main entry point for drain command."""
    print("Draining all pending sessions...")
    sessions, notes = drain_all()
    print(f"Done: {sessions} sessions processed, {notes} notes written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
