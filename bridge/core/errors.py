"""Unified exception definitions for SpecPowers bridge."""


class SpecPowersError(Exception):
    """Base exception for all SpecPowers errors."""
    exit_code: int = 1

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.detail = detail


class FatalError(SpecPowersError):
    """Fatal error — terminate immediately, state unchanged, requires manual intervention."""
    exit_code = 2


class RecoverableError(SpecPowersError):
    """
    Recoverable error — pipeline can continue but with warnings.
    Exit code 0, warning written to stderr.
    """
    exit_code = 0


class GitNotFoundError(FatalError):
    """git is not installed or not available in PATH."""
    pass


class NotGitRepoError(FatalError):
    """Current directory is not a git repository."""
    pass


class DetachedHeadError(FatalError):
    """Git repository is in detached HEAD state with no commits."""
    pass


class EmptyRepoError(FatalError):
    """Git repository has no commits yet."""
    pass


class LockAcquireError(FatalError):
    """Failed to acquire file lock (another instance may be running)."""
    pass


class StateError(FatalError):
    """Invalid state machine transition."""
    pass


class ArtifactMissingError(FatalError):
    """Required artifact not found — cannot proceed."""
    pass


class BaselineError(RecoverableError):
    """Baseline is stale or corrupted, but pipeline may continue."""
    pass


class ArchiveDuplicateError(FatalError):
    """Feature already archived — reject duplicate archive."""
    pass


class MergeCheckError(RecoverableError):
    """Merge check triggered — requires manual review."""
    pass
