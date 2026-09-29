"""``conformance_mock`` profile (Layer 3).

Runs only protocol conformance, never scores. Hosts the ``ScriptedTestBackend``
(moved from the kernel's ``model_backend.py`` in Phase 4) and a scripted adapter
that drives every event in the public stream deterministically.

The concrete ``adapter.py``/``scripted_backend.py`` are implemented in Phase 4
(conformance suite); this package is stubbed here for registry/import stability.
"""
