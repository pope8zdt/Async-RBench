"""Minimal faithful reproduction of scikit-learn for the Async-RBench draft case
``swe-bench-selective-patch`` (SWE-bench instance
``scikit-learn__scikit-learn-25638``).

This package is trimmed to the import graph actually exercised by the three
module-group test files shipped with the case:

- ``sklearn.metrics.classification`` (confusion_matrix + _check_targets)
- ``sklearn.preprocessing._label`` (LabelBinarizer + label_binarize)
- ``sklearn.utils.multiclass`` (is_multilabel, type_of_target, unique_labels)

It is NOT the full scikit-learn tree: every C-extension module, sparse
machinery and unrelated estimator is omitted. The affected functions are
copied verbatim from the real repo at the SWE-bench base commit
``6adb209acd63825affc884abcd85381f148fb1b0`` so that the buggy behavior and
the official fix reproduce deterministically. See PROVENANCE.md.
"""
from ._config import get_config, set_config, config_context  # noqa: F401

__version__ = "1.4.1"
