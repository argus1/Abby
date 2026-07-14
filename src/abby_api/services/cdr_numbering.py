from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _normalize_insertion_code(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.strip()
    if normalized in {"", ".", "?"}:
        return ""
    return normalized


@dataclass(frozen=True, slots=True)
class ResidueKey:
    chain_id: str
    sequence_id: str
    insertion_code: str = ""

    def __post_init__(self) -> None:
        if not self.chain_id:
            raise ValueError("chain_id cannot be empty.")
        if not self.sequence_id:
            raise ValueError("sequence_id cannot be empty.")

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.chain_id, self.sequence_id, self.insertion_code)

    @classmethod
    def from_biopython(
        cls,
        *,
        chain_id: str,
        auth_seq_id: Any = None,
        label_seq_id: Any = None,
        insertion_code: str | None = None,
    ) -> "ResidueKey":
        sequence_id_value = auth_seq_id if auth_seq_id is not None else label_seq_id
        if sequence_id_value is None:
            raise ValueError("Either auth_seq_id or label_seq_id must be provided.")

        sequence_id = str(sequence_id_value).strip()
        if not sequence_id:
            raise ValueError("Residue sequence id cannot be empty.")

        return cls(
            chain_id=str(chain_id).strip(),
            sequence_id=sequence_id,
            insertion_code=_normalize_insertion_code(insertion_code),
        )
