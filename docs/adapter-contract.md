# Adapter contract

The adapter implements the evaluated main agent and subagents behind protocol 3.0. It receives only public task/workstream/artifact information and gateway outcomes. It must not access case-private files or evaluator traces.

The adapter reports child lifecycle and payloads without assigning `result_kind`. It explicitly acknowledges delivered results before using them, records promotion outcomes, and declares artifact lineage only from consumed completion IDs.

All workspace operations go through kernel capability RPC. `observe_artifact` and `verify_current_state` are evaluator-mediated: the adapter supplies only public IDs and lineage, never commands. Raw capability messages are transport and are excluded from the event source.

Track A uses the repository’s fixed reference API adapter. A custom adapter is allowed only for development and is never official-leaderboard eligible.
