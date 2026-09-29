"""Minimal classification metrics (module group A fix target surface).

Only ``confusion_matrix`` is implemented. The implementation is a faithful
structural re-derivation of the corresponding scikit-learn code path: it asks
``sklearn.utils.multiclass`` for the target type and label set, then builds the
confusion matrix from those labels. Module group A's tests exercise this module
with plain (non-nullable) integer and string labels.
"""

import numpy as np

from ..utils.multiclass import type_of_target, unique_labels
from ..utils.validation import check_consistent_length


def _check_targets(y_true, y_pred):
    """Validate that the two targets are single-label classification targets."""
    y_type_1 = type_of_target(y_true, input_name="y_true")
    y_type_2 = type_of_target(y_pred, input_name="y_pred")
    if y_type_1 not in ("binary", "multiclass"):
        raise ValueError(
            "Classification metrics can't handle a mix of continuous and "
            f"multiclass targets. Got {y_type_1!r} for y_true."
        )
    if y_type_2 not in ("binary", "multiclass"):
        raise ValueError(
            "Classification metrics can't handle a mix of continuous and "
            f"multiclass targets. Got {y_type_2!r} for y_pred."
        )
    if y_type_1 != y_type_2:
        raise ValueError("Mix of binary and multiclass targets")
    check_consistent_length(y_true, y_pred)
    return y_type_1, np.asarray(y_true), np.asarray(y_pred)


def confusion_matrix(y_true, y_pred):
    """Compute the confusion matrix to evaluate the accuracy of a classification.

    The row index and the column index of the returned matrix follow the
    ordered set of labels shared by ``y_true`` and ``y_pred``, exactly as in
    scikit-learn's ``confusion_matrix`` (without sample weighting).
    """
    y_type, y_true, y_pred = _check_targets(y_true, y_pred)
    labels = unique_labels(y_true, y_pred)
    n_labels = labels.size

    label_to_ind = {label: index for index, label in enumerate(labels)}
    y_ind = np.array([label_to_ind.get(label, n_labels) for label in y_true])
    p_ind = np.array([label_to_ind.get(label, n_labels) for label in y_pred])

    matrix = np.zeros((n_labels, n_labels), dtype=np.int64)
    for row, col in zip(y_ind, p_ind):
        if row < n_labels and col < n_labels:
            matrix[row, col] += 1
    return matrix
