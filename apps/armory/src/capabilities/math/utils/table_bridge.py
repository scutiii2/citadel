"""Caller-scoped immutable table pages; never use rounded display-cell output."""

from src.capabilities.math.contract import RESERVED, TableFormulaInput, TablePageInfo


class TableBridge:
    def __init__(self, registry, owner):
        self.registry = registry
        self.owner = owner

    def prepare(self, data):
        """Run on a thread: registry locks and bounded row copies stay off the loop."""
        spec = TableFormulaInput.model_validate(data.model_dump() if hasattr(data, "model_dump") else data)
        table = self.registry.get(spec.table_id, self.owner)
        if table is None:
            raise ValueError("Table unavailable for current caller.")
        mapping = {}
        for name, column in spec.columns.items():
            if name in RESERVED or column not in table.columns:
                raise ValueError("Column mapping needs non-reserved variable names and exact existing column names.")
            index = table.columns.index(column)
            if table.kinds[index] != "number":
                raise ValueError(f"Column {column!r} is not numeric; choose a numeric column.")
            mapping[name] = index
        end = min(table.row_count, spec.offset + spec.limit)
        records = []
        for index in range(spec.offset, end):
            bindings = {binding.name: binding.model_dump() for binding in spec.bindings}
            for name, column in mapping.items():
                bindings[name] = {"type": "constant", "name": name, "value": table.data[column][index]}
            records.append({"id": str(index + 1), "data": list(bindings.values())})
        return records, TablePageInfo(table_id=table.id, offset=spec.offset, rows=len(records), total_rows=table.row_count,
                                       next_offset=end if end < table.row_count else None)
