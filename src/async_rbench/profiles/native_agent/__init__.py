"""``native_agent`` profile (Layer 3).

A participant's own full agent system: reads ``episode_started``, emits the same
public event stream as the reference scaffold, and drives its own model backend
and tool router while calling kernel capability RPCs (``spawn_child``/``fork``/
``commit``) over the standard stdio shim.

The concrete ``adapter.py`` is implemented in Phase 6 (runtime modes). This
package is stubbed here so the profile registry and import boundary are stable.
"""
