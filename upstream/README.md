# Upstream source trees

Case bundles are self-contained: each case under `data/async-rbench/cases/`
carries the assets it needs, and the benchmark does not require anything from
this directory.

This directory is where upstream source trees are placed when a case is being
authored or audited against its original task. It is ignored by git
(`/upstream/*` in `.gitignore`, with this file excepted), so a checkout stays
small and no upstream tree is redistributed from here.

To work on a case against its upstream source, place that tree under
`upstream/` locally. `PROVENANCE.md` in the case directory records which
upstream material the case derives from.
