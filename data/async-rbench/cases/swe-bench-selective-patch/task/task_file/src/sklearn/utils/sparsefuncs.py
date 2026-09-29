"""Minimal sparse helper functions used by the trimmed sklearn reproduction.

``min_max_axis`` is used by ``_inverse_binarize_multiclass`` (only on the
sparse branch, which the case's tests never hit). Implemented generically over
both dense arrays and scipy sparse matrices.
"""


def min_max_axis(X, axis):
    """Compute the minimum and maximum along the given axis."""
    return X.min(axis=axis), X.max(axis=axis)
