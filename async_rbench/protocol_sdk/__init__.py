"""Participant-facing protocol SDK.

The SDK is a convenience layer over the JSONL event protocol; its correctness is
guaranteed by emitting only events that pass ``validate_adapter_event``.
"""

from .gateway import JsonlGateway, configure_utf8_stdio

__all__ = ["JsonlGateway", "configure_utf8_stdio"]
