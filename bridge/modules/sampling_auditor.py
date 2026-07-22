"""Sampling auditor — structured audit logging with stratified sampling.

Rules:
- Every gate decision is logged (JSONL).
- Sampling: max(10% random, at least 1 in every 20).
- seq is monotonically increasing.
"""

import json
import random
from datetime import datetime, timezone
from pathlib import Path


def _get_audit_path(root: Path) -> Path:
    return root / ".specpowers" / "audit.log"


def _get_next_seq(audit_path: Path) -> int:
    """Get the next sequence number by reading the last entry."""
    if not audit_path.exists():
        return 1

    last_seq = 0
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                seq = entry.get("seq", 0)
                if seq > last_seq:
                    last_seq = seq
            except json.JSONDecodeError:
                pass

    return last_seq + 1


def log_audit(root: Path, ts: str, stage: str, result: str,
             signals: list[str], confidence: str, git_ref: str) -> int:
    """Write an audit log entry.

    Args:
        root: Project root.
        ts: ISO timestamp.
        stage: Pipeline stage.
        result: Gate result (pass / escalate / reject).
        signals: Detected signals.
        confidence: Confidence level.
        git_ref: Current HEAD ref.

    Returns:
        Sequence number of this entry.
    """
    audit_path = _get_audit_path(root)
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    seq = _get_next_seq(audit_path)
    sampled = should_sample(seq)

    entry = {
        "seq": seq,
        "ts": ts,
        "stage": stage,
        "gate": {
            "result": result,
            "signals": signals,
            "confidence": confidence,
            "sampled": sampled,
        },
        "git_ref": git_ref,
    }

    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return seq


def should_sample(seq: int) -> bool:
    """Determine if this entry should be sampled.

    Sampling rule: max(10% random chance, at least 1 in every 20).
    """
    # Random 10%
    if random.random() < 0.10:
        return True

    # Force every 20th
    if seq > 0 and seq % 20 == 0:
        return True

    return False


def should_force(seq: int) -> bool:
    """Check if forced sampling should kick in for this seq.

    This is called to ensure the "at least 1 in 20" rule.
    """
    return seq > 0 and seq % 20 == 0


def read_recent(root: Path, n: int = 20) -> list[dict]:
    """Read the last N audit log entries."""
    audit_path = _get_audit_path(root)
    if not audit_path.exists():
        return []

    entries = []
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

    return entries[-n:]


def get_sampled_count(root: Path) -> int:
    """Count sampled entries in audit.log."""
    audit_path = _get_audit_path(root)
    if not audit_path.exists():
        return 0

    count = 0
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("gate", {}).get("sampled", False):
                    count += 1
            except json.JSONDecodeError:
                pass

    return count


def check_sampling_health(root: Path) -> bool:
    """Check if sampling rate is healthy (>0 sampled in last 50 entries).

    Returns True if healthy.
    """
    recent = read_recent(root, 50)
    sampled_count = sum(
        1 for e in recent
        if e.get("gate", {}).get("sampled", False)
    )
    return sampled_count > 0 or len(recent) < 20
