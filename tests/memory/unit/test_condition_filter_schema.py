import pytest
from pydantic import ValidationError

from lumneo.memory.model import MemoryNeed


@pytest.mark.parametrize(
    "condition_filter",
    [
        {"key": "place", "value": "客厅"},
        {
            "operator": "AND",
            "clauses": [
                {"key": "place", "value": "客厅"},
                {"key": "time", "value": "周末"},
            ],
        },
    ],
)
def test_memory_need_accepts_frozen_condition_filter_shapes(
    condition_filter: dict,
) -> None:
    assert MemoryNeed(condition_filter=condition_filter).condition_filter == condition_filter


@pytest.mark.parametrize(
    "condition_filter",
    [
        {},
        {"key": "place", "value": "客厅", "extra": True},
        {"operator": "OR", "clauses": [{"key": "place", "value": "客厅"}]},
        {"operator": "AND", "clauses": []},
        {
            "operator": "AND",
            "clauses": [
                {"key": str(index), "value": str(index)} for index in range(6)
            ],
        },
    ],
)
def test_memory_need_rejects_non_contract_condition_filter_shapes(
    condition_filter: dict,
) -> None:
    with pytest.raises(ValidationError):
        MemoryNeed(condition_filter=condition_filter)

