from __future__ import annotations

import importlib
from typing import TypeVar


T = TypeVar("T")


def load_component(spec: str, expected: type[T]) -> T:
    module_name, separator, factory_name = spec.partition(":")
    if (
        not separator
        or not module_name
        or module_name.startswith(".")
        or not factory_name
    ):
        raise ValueError("component entry point must be an absolute module:factory")
    module = importlib.import_module(module_name)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise ValueError(f"component factory is not callable: {spec}")
    component = factory()
    if not isinstance(component, expected):
        raise ValueError(f"component does not implement {expected.__name__}: {spec}")
    return component
