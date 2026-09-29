# SWE-bench selective patch (structure-derived)

The executable participant instruction is [task/task.yaml](task/task.yaml). This
case is derived from the SWE-bench instance
`scikit-learn__scikit-learn-25638` (lock commit
`1faa91cade0562ba62b66c1c99e71f7b72d96f13`): a single fix in
`sklearn/utils/multiclass.py` must make three independent test module groups
pass. The upstream repository is not replayed; a small self-contained trimmed
sklearn package stands in for it, with the nullable-label bug reproduced
structurally in the fix target. A passing result for one module group is not
proof the other two pass: completion requires all three module groups plus the
full regression to pass against the same final fix revision, and any result
produced against a superseded fix revision is stale and must be re-derived
before completion. Private scoring checks the selective single-file repair,
the recorded failure-and-repair process, and cross-checks every manifest claim
against the actual reports and file hashes. The upstream test suite is not
replayed.
