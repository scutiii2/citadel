"""Remove presentation annotations from model-bound JSON schemas."""

from typing import Any


_SCHEMA_MAPS = {"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"}
_SCHEMA_LISTS = {"allOf", "anyOf", "oneOf", "prefixItems"}
_SCHEMA_NODES = {"items", "additionalItems", "additionalProperties", "unevaluatedProperties", "unevaluatedItems",
                 "contains", "propertyNames", "not", "if", "then", "else", "contentSchema"}


def model_schema(schema: Any) -> Any:
    """Copy schema nodes without removing parameter names or example data."""
    if not isinstance(schema, dict):
        return schema
    result = {}
    for key, value in schema.items():
        if key == "input":
            continue
        if key in _SCHEMA_MAPS and isinstance(value, dict):
            value = {name: model_schema(node) for name, node in value.items()}
        elif key in _SCHEMA_LISTS and isinstance(value, list):
            value = [model_schema(node) for node in value]
        elif key == "items" and isinstance(value, list):
            value = [model_schema(node) for node in value]
        elif key in _SCHEMA_NODES:
            value = model_schema(value)
        elif key == "dependencies" and isinstance(value, dict):
            value = {name: model_schema(node) for name, node in value.items()}
        result[key] = value
    return result
