from __future__ import annotations


def reflect(
    what_learned: str,
    what_evidence: str,
    what_missing: str,
    next_action: str,
) -> str:
    """Pause to reflect on research progress.

    Call this tool to explicitly organise your thinking before deciding what
    to do next.  It does not perform any external action — it helps you
    structure your internal reasoning.

    Args:
        what_learned: Key facts and conclusions discovered so far.
        what_evidence: Specific evidence and sources already collected
            (include citation URLs where known).
        what_missing: Information that is still absent or uncertain.
        next_action: The concrete action you plan to take next
            (e.g. "search for X", "read URL Y", "write final summary").

    Returns:
        A structured reflection summary.
    """
    return (
        "=== Research Reflection ===\n"
        f"What I've learned: {what_learned}\n"
        f"Evidence collected: {what_evidence}\n"
        f"Still missing: {what_missing}\n"
        f"Next action: {next_action}\n"
        "==========================="
    )
