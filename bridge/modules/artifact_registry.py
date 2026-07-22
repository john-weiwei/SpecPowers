"""Artifact registry — defines all pipeline artifacts and their relationships.

Each artifact has:
- layer: "cognitive" or "deterministic"
- path: relative path from repo root
- producer: stage that creates this artifact
- consumers: stages that read this artifact
- required: True (always required) or {"full": True, "fast": False} (mode-dependent)
"""

from typing import TypedDict


class Artifact(TypedDict):
    layer: str
    path: str
    producer: str
    consumers: list[str]
    required: bool | dict


MANIFEST: list[Artifact] = [
    {
        "layer": "cognitive",
        "path": "constitution.md",
        "producer": "constitution",
        "consumers": ["brainstorm", "specify", "plan", "build", "archive"],
        "required": True,
    },
    {
        "layer": "cognitive",
        "path": "brief.md",
        "producer": "brainstorm",
        "consumers": ["specify"],
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "cognitive",
        "path": "spec.md",
        "producer": "specify",
        "consumers": ["plan", "build"],
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "cognitive",
        "path": "plan.md",
        "producer": "plan",
        "consumers": ["build"],
        "required": {"full": True, "fast": False},
    },
    {
        "layer": "deterministic",
        "path": ".specpowers/baseline.json",
        "producer": "constitution",
        "consumers": ["build", "archive", "baseline"],
        "required": True,
    },
    {
        "layer": "deterministic",
        "path": ".specpowers/state.json",
        "producer": "constitution",
        "consumers": ["*"],
        "required": True,
    },
]


def required_for(stage: str, mode: str) -> list[Artifact]:
    """Return artifacts required before entering a given stage.

    Args:
        stage: Target stage name.
        mode: Operation mode (full / fast).

    Returns:
        List of required artifacts.
    """
    required = []
    for art in MANIFEST:
        if stage in art["consumers"] or "*" in art["consumers"]:
            req = art["required"]
            if isinstance(req, dict):
                if req.get(mode, True):
                    required.append(art)
            elif req:
                required.append(art)
    return required


def has_consumer(artifact: Artifact) -> bool:
    """Check if an artifact has consumers (value gate guardian).

    Delayed consumers (e.g., trace/audit) count as valid consumers.
    """
    consumers = artifact.get("consumers", [])
    return len(consumers) > 0


def get_artifact(path: str) -> Artifact | None:
    """Find an artifact by its path."""
    for art in MANIFEST:
        if art["path"] == path:
            return art
    return None


def list_by_producer(stage: str) -> list[Artifact]:
    """List artifacts produced by a given stage."""
    return [art for art in MANIFEST if art["producer"] == stage]


def list_by_consumer(stage: str) -> list[Artifact]:
    """List artifacts consumed by a given stage."""
    result = []
    for art in MANIFEST:
        if stage in art["consumers"] or "*" in art["consumers"]:
            result.append(art)
    return result
