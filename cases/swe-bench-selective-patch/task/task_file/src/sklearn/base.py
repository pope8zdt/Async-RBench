"""Minimal BaseEstimator / TransformerMixin / clone for the trimmed sklearn.

Only the plumbing actually reached by the case's three module groups is kept:
``fit``/``transform`` parameter plumbing and the ``_validate_params`` hook used
by ``LabelBinarizer.fit``. Docstrings and estimator pretty-printing machinery
are omitted.
"""
import copy
import inspect
from collections import defaultdict
from numbers import Integral

import numpy as np


def clone(estimator, *, safe=True):
    """Construct a new unfitted estimator with the same parameters.

    Minimal implementation sufficient for the trimmed package. Only used
    internally; not exercised by the case's module groups.
    """
    if isinstance(estimator, (list, tuple, set, frozenset)):
        return type(estimator)([clone(e, safe=safe) for e in estimator])
    if not hasattr(estimator, "get_params") or isinstance(estimator, type):
        if not safe:
            return copy.copy(estimator)
        raise TypeError(
            "Cannot clone object %r (type %s): it does not seem to be a "
            "scikit-learn estimator as it does not implement a 'get_params' "
            "method." % (estimator, type(estimator))
        )
    klass = estimator.__class__
    new_object_params = estimator.get_params(deep=False)
    for name, param in new_object_params.items():
        new_object_params[name] = clone(param, safe=False)
    new_object = klass(**new_object_params)
    params_set = new_object.get_params(deep=False)
    for name in new_object_params:
        param1 = new_object_params[name]
        param2 = params_set[name]
        if param1 is not param2:
            raise RuntimeError(
                "Cannot clone object %r, as the constructor either does not set "
                "or modifies parameter %s" % (estimator, name)
            )
    return new_object


class BaseEstimator:
    """Base class for all estimators in the trimmed sklearn reproduction."""

    @classmethod
    def _get_param_names(cls):
        init = cls.__init__
        if init is object.__init__:
            return []
        init_signature = inspect.signature(init)
        parameters = [
            p
            for p in init_signature.parameters.values()
            if p.name != "self" and p.kind != p.VAR_KEYWORD
        ]
        for p in parameters:
            if p.kind == p.VAR_POSITIONAL:
                raise RuntimeError(
                    "scikit-learn estimators should always specify their "
                    "parameters in the signature of their __init__ (no varargs)."
                )
        return sorted([p.name for p in parameters])

    def get_params(self, deep=True):
        out = dict()
        for key in self._get_param_names():
            value = getattr(self, key)
            if deep and hasattr(value, "get_params") and not isinstance(value, type):
                deep_items = value.get_params().items()
                out.update((key + "__" + k, val) for k, val in deep_items)
            out[key] = value
        return out

    def set_params(self, **params):
        if not params:
            return self
        valid_params = self.get_params(deep=True)
        nested_params = defaultdict(dict)
        for key, value in params.items():
            key, delim, sub_key = key.partition("__")
            if key not in valid_params:
                raise ValueError(
                    "Invalid parameter %s for estimator %s. Valid parameters are: %s."
                    % (key, self, sorted(valid_params.keys()))
                )
            if delim:
                nested_params[key][sub_key] = value
            else:
                setattr(self, key, value)
                valid_params[key] = value
        for key, sub_params in nested_params.items():
            valid_params[key].set_params(**sub_params)
        return self

    def _validate_params(self):
        """Validate the estimator's parameters against _parameter_constraints.

        Minimal version of the 1.4-era constraint validation. It accepts the
        (valid) defaults used by the estimators in this trimmed package; it is
        only reached by ``LabelBinarizer.fit``.
        """
        constraints = getattr(self, "_parameter_constraints", None)
        if not constraints:
            return
        for name, value in vars(self).items():
            if name not in constraints:
                continue
            allowed = constraints[name]
            ok = False
            for constraint in allowed:
                if isinstance(constraint, type):
                    ok = ok or isinstance(value, constraint)
                elif constraint == "boolean":
                    ok = ok or isinstance(value, bool)
                elif constraint == "integral":
                    ok = ok or isinstance(value, Integral)
                elif constraint == "array-like":
                    ok = ok or value is None or hasattr(value, "__len__")
                elif constraint == "str":
                    ok = ok or isinstance(value, str)
                else:
                    # unknown constraint; do not fail closed on it
                    ok = ok or value is None
            if not ok:
                raise ValueError(
                    f"Invalid parameter {name!r} for estimator {self}. Valid "
                    f"parameter values are: {allowed}"
                )

    def __repr__(self):
        return f"{self.__class__.__name__}()"


class TransformerMixin:
    """Mixin class for all transformers."""

    def fit_transform(self, X, y=None, **fit_params):
        if y is None:
            return self.fit(X, **fit_params).transform(X)
        else:
            return self.fit(X, y, **fit_params).transform(X)

    def __sklearn_clone__(self):
        return clone(self)
