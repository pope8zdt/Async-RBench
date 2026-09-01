"""Module group B — sklearn.preprocessing (test_label).

These tests exercise the NULLABLE-label path of ``LabelBinarizer``. A nullable
label array is represented, in this NumPy-only trimmed package, as an
object-dtype array whose entries are integer labels plus a ``None`` missing
marker (the structural stand-in for a pandas nullable integer column).

After a correct fix to the fix target ``sklearn/utils/multiclass.py``,
``LabelBinarizer`` must fit, transform and round-trip the nullable labels with
the missing entry treated as the negative class.
"""

import numpy as np

from sklearn.preprocessing import LabelBinarizer


def _nullable_labels():
    # Nullable integer labels: two real classes plus one missing marker.
    return np.array([1, 2, None, 1], dtype=object)


def test_label_binarizer_nullable_fit():
    y = _nullable_labels()
    lb = LabelBinarizer().fit(y)
    assert lb.y_type_ == "binary"
    assert lb.classes_.tolist() == [1, 2]


def test_label_binarizer_nullable_transform():
    y = _nullable_labels()
    lb = LabelBinarizer().fit(y)
    encoded = lb.transform(y)
    assert encoded.shape == (4, 1)
    # Binary binarization encodes the positive class (2) as 1; the missing
    # marker is not in the fitted classes and is encoded as the negative class.
    assert encoded.ravel().tolist() == [0, 1, 0, 0]


def test_label_binarizer_nullable_round_trip():
    y = _nullable_labels()
    lb = LabelBinarizer().fit(y)
    encoded = lb.transform(y)
    decoded = lb.inverse_transform(encoded)
    assert decoded.tolist() == [1, 2, 1, 1]
