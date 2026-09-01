"""Module group A — sklearn.metrics (test_classification).

These tests exercise the metrics surface with PLAIN integer and string labels.
A valid fix to the fix target ``sklearn/utils/multiclass.py`` must not regress
the plain (non-nullable) target-type path.
"""

import numpy as np
import pytest

from sklearn.metrics import confusion_matrix


def test_confusion_matrix_plain_integers():
    y_true = np.array([1, 2, 3, 1])
    y_pred = np.array([3, 2, 1, 1])
    matrix = confusion_matrix(y_true, y_pred)
    assert matrix.shape == (3, 3)
    assert matrix.sum() == 4
    assert matrix[0, 0] == 1  # true 1 predicted 1
    assert matrix[0, 2] == 1  # true 1 predicted 3
    assert matrix[1, 1] == 1  # true 2 predicted 2
    assert matrix[2, 0] == 1  # true 3 predicted 1


def test_confusion_matrix_binary_strings():
    y_true = ["cat", "dog", "cat", "dog", "cat"]
    y_pred = ["cat", "cat", "dog", "dog", "cat"]
    matrix = confusion_matrix(y_true, y_pred)
    assert matrix.shape == (2, 2)
    assert matrix[0, 0] == 2
    assert matrix[0, 1] == 1
    assert matrix[1, 0] == 1
    assert matrix[1, 1] == 1


def test_confusion_matrix_rejects_mixed_target_types():
    y_true = [0, 1, 1, 0]
    y_pred = [0.2, 0.8, 0.1, 0.9]
    with pytest.raises(ValueError, match="continuous"):
        confusion_matrix(y_true, y_pred)
