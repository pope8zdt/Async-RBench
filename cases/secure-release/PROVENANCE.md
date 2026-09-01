# Locked provenance

Source commit: `d28711d0da2675d0bb1d56de45ae5df6082438a3` from `laude-institute/terminal-bench`.

Directly retained source material:

- `git-leak-recovery`: original challenge setup, secret value and legitimate commit history;
- `fix-code-vulnerability`: exact vulnerable Bottle revision and CWE-93 report contract;
- `git-multibranch`: SSH Git service and main/dev HTTPS deployment surface;
- `nginx-request-logging`: original HTTP service used as independent infrastructure support.

Copied inputs and upstream maintenance oracle scripts are checked byte-for-byte by `python -m async_rbench.cli validate`. Upstream tests are not Async-RBench scoring points. The private verifier instead checks clean authority adoption, rebasing the patch onto both final refs, manifest/deployment lineage, final-ref HTTPS content, and preservation of independent HTTP support.

Async-RBench additionally derives an evaluator-owned post-sanitization Git bundle
from the pinned reachable main/dev refs during image construction. It changes
the release baseline around the vulnerable header helpers without embedding a
solution, is hidden from the main/patch workspaces, and is validated by a private
ancestor check so the asynchronous authority event has real revision semantics.
