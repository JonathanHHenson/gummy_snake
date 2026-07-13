from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from benchmarks.schema.canonical import (
    CanonicalJsonError,
    canonical_json,
    canonical_json_loads,
    content_hash,
    definition_digest,
)


def test_canonical_json_sorts_keys_encodes_decimals_and_has_one_newline() -> None:
    payload = canonical_json({"z": Decimal("1.250"), "a": [3, 2, 1]})

    assert payload == b'{"a":[3,2,1],"z":"1.250"}\n'
    assert canonical_json_loads(payload) == {"a": [3, 2, 1], "z": "1.250"}
    assert content_hash({"z": Decimal("1.250"), "a": [3, 2, 1]}) == content_hash(
        {"a": [3, 2, 1], "z": Decimal("1.250")}
    )


@pytest.mark.parametrize(
    "payload, message",
    [
        (b'{"value":1.5}\n', "binary-float"),
        (b'{"value":NaN}\n', "non-finite"),
        (b'{"a":1,"a":2}\n', "duplicate"),
        (b'{"b":1, "a":2}\n', "not canonical"),
        (b'{"a":1}\n\n', "not canonical"),
        (b'\xef\xbb\xbf{"a":1}\n', "byte-order mark"),
    ],
)
def test_strict_canonical_parser_rejects_ambiguous_or_noncanonical_json(
    payload: bytes, message: str
) -> None:
    with pytest.raises(CanonicalJsonError, match=message):
        canonical_json_loads(payload)


def test_definition_digest_covers_entry_and_exact_declared_file_bytes(tmp_path: Path) -> None:
    workload = tmp_path / "work.py"
    workload.write_bytes(b"print('one')\n")
    first = definition_digest({"id": "draw", "version": 1}, {"work.py": workload})

    workload.write_bytes(b"print('two')\n")
    second = definition_digest({"id": "draw", "version": 1}, {"work.py": workload})
    third = definition_digest({"id": "draw", "version": 2}, {"work.py": workload})

    assert first.startswith("sha256:")
    assert len(first) == 71
    assert len({first, second, third}) == 3
