# Adapter contract

> Paper experiment / 论文实验：统计冻结的 200-task evaluation set；Batched/Async
> 各运行 3 次，即每模型每模式 600 次、两种模式合计 1,200 次。47 个构造任务与
> evaluation set 不重叠，也不进入论文结果。

The adapter implements the evaluated main agent and subagents behind protocol 3.0. It receives only public task/workstream/artifact information and gateway outcomes. It must not access case-private files or evaluator traces.

The adapter reports child lifecycle and payloads without assigning `result_kind`. It explicitly acknowledges delivered results before using them, records promotion outcomes, and declares artifact lineage only from consumed completion IDs.

All workspace operations go through kernel capability RPC. `observe_artifact` and `verify_current_state` are evaluator-mediated: the adapter supplies only public IDs and lineage, never commands. Raw capability messages are transport and are excluded from the event source.

The formal paper evaluation uses the repository's fixed reference API adapter.
Custom adapters are supported for development and protocol conformance but are
not part of the paper comparison.
