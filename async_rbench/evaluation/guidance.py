from __future__ import annotations


GUIDANCE_MODES = ("none", "protocol", "incentive")


def render_guidance(mode: str) -> str:
    if mode not in GUIDANCE_MODES:
        raise ValueError(f"unknown guidance mode {mode!r}")
    if mode == "none":
        return (
            "The benchmark gateway delivers child-workstream messages. Complete the user task "
            "using the available tools and the evidence you judge relevant."
        )
    protocol = (
        "The benchmark has already started the declared workstreams. Their messages are delivered "
        "through the result gateway and can include provenance and version metadata. The available "
        "tools expose status and result-management operations; choose how to use them from the task "
        "state rather than from benchmark guidance."
    )
    if mode == "protocol":
        return protocol
    return protocol + (
        " Evaluation credit comes from independently verified task outcomes and protocol records; "
        "calling a tool by itself does not establish correctness."
    )
