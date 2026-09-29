"""Module group C — sklearn.utils.multiclass (test_multiclass).

These tests exercise the target-type and label utilities directly with PLAIN
(non-nullable) inputs. A valid fix must not regress the plain target-type path.
"""

import numpy as np

from sklearn.utils.multiclass import type_of_target, unique_labels


def test_type_of_target_plain_multiclass():
    assert type_of_target([1, 2, 3]) == "multiclass"
    assert type_of_target(np.array([1, 2, 3])) == "multiclass"
    assert type_of_target([1.0, 2.0, 3.0]) == "multiclass"


def test_type_of_target_plain_binary():
    assert type_of_target([1, -1, 1]) == "binary"
    assert type_of_target(["a", "b", "a"]) == "binary"


def test_type_of_target_continuous():
    assert type_of_target([0.2, 0.8, 0.1]) == "continuous"


def test_unique_labels_plain():
    labels = unique_labels([1, 2], [2, 3], [1, 3])
    assert labels.tolist() == [1, 2, 3]
    assert unique_labels([3, 5, 5, 5, 7, 7]).tolist() == [3, 5, 7]
