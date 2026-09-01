"""Full-package smoke regression (runs last, after every module group).

A minimal end-to-end pass over the three public surfaces with plain inputs,
plus one check that the fix target's module is importable. This is the
regression suite's final gate: every module group must still work together.
"""

import numpy as np

from sklearn.metrics import confusion_matrix
from sklearn.preprocessing import LabelBinarizer
from sklearn.utils.multiclass import unique_labels


def test_smoke_pipeline():
    y_true = np.array([0, 1, 0, 1, 0])
    y_pred = np.array([0, 0, 1, 1, 0])
    matrix = confusion_matrix(y_true, y_pred)
    assert matrix.shape == (2, 2)
    assert matrix[0, 0] == 2

    labels = unique_labels([0, 1], [1, 2])
    assert labels.tolist() == [0, 1, 2]

    lb = LabelBinarizer().fit([0, 1, 0, 1])
    assert lb.classes_.tolist() == [0, 1]
    encoded = lb.transform([0, 1, 0, 1])
    assert encoded.shape == (4, 1)
