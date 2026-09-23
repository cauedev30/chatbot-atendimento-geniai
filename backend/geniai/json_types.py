"""Pydantic types for decoded JSON: strict types, with integral numbers accepted as integers."""

from typing import Annotated

from pydantic import BeforeValidator, StrictInt


def _integral_float_to_int(value: object) -> object:
    # JSON has one number type, so 2.0 counts as the integer 2.
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


JsonInt = Annotated[StrictInt, BeforeValidator(_integral_float_to_int)]
"""An integer JSON number; strings, booleans and fractions are rejected."""
