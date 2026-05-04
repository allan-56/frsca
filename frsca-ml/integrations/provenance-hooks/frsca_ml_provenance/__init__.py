"""
FRSCA-ML Provenance Hooks

Drop-in provenance capture for existing ML platforms.
"""

from .provenance_hook import capture, resolve_artifact

__all__ = ["capture", "resolve_artifact"]
