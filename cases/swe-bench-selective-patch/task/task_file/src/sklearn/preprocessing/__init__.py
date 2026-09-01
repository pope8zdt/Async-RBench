"""Preprocessing transformers for the trimmed sklearn package.

This is module group B's surface. ``LabelBinarizer`` (and its backing
``label_binarize`` helper) is the piece whose nullable-label code path is
repaired by the case's fix.
"""

from ._label import LabelBinarizer, label_binarize

__all__ = ["LabelBinarizer", "label_binarize"]
