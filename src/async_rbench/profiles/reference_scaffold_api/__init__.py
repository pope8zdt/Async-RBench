"""Thin, model-agnostic reference agent scaffold profile (api-only)."""

from .config import ScaffoldConfig
from .runtime import ReferenceScaffold

__all__ = ["ReferenceScaffold", "ScaffoldConfig"]
