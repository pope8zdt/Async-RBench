"""Classification metrics for the trimmed sklearn package.

This is module group A's surface. It is deliberately small: only the pieces
used by the case's module-group tests are implemented. The implementation
relies on ``sklearn.utils.multiclass.type_of_target`` and ``unique_labels``
(see ``sklearn/utils/multiclass.py``) for target-type inference.
"""

from ._classification import confusion_matrix

__all__ = ["confusion_matrix"]
