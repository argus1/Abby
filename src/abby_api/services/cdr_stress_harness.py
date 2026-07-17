from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_POINT_MUTATION_RE = re.compile(
    r"^(?P<chain>[A-Za-z0-9]+):(?P<seq_id>\d+)(?P<icode>[A-Za-z]?):"
    r"(?P<from>[A-Z])>(?P<to>[A-Z])$"
)
_RANGE_MUTATION_RE = re.compile(
    r"^(?P<chain>[A-Za-z0-9]+):(?P<start>\d+)-(?P<end>\d+):(?P<to>[A-Z])$"
)
_MAX_RANGE_SPAN = 64


@dataclass(frozen=True)
class CDRMutationSpec:
    chain_id: str
    start_seq_id: int
    end_seq_id: int
    insertion_code: str
    from_residue: str | None
    to_residue: str
    mode: Literal["point_substitution", "range_substitution"]


@dataclass(frozen=True)
class CDRStressCaseResult:
    input_spec: str
    status: Literal["parsed", "failed"]
    parsed_spec: CDRMutationSpec | None = None
    error: str | None = None


@dataclass(frozen=True)
class CDRStressBatchSummary:
    total_specs: int
    parsed_specs: int
    failed_specs: int
    results: list[CDRStressCaseResult]


def parse_cdr_mutation_spec(text: str) -> CDRMutationSpec:
    """Parse a single CDR-local mutation specification.

    Current scaffold supports point substitutions in the format:
    ``CHAIN:SEQ[ICODE]:FROM>TO`` (example: ``H:95A:C>W``).
    """

    candidate = str(text or "").strip()

    range_match = _RANGE_MUTATION_RE.match(candidate)
    if range_match is not None:
        chain_id = range_match.group("chain")
        start_seq_id = int(range_match.group("start"))
        end_seq_id = int(range_match.group("end"))
        to_residue = range_match.group("to")

        if start_seq_id <= 0 or end_seq_id <= 0:
            raise ValueError(
                "CDR_MUTATION_RANGE_INVALID: sequence indices must be positive integers"
            )
        if end_seq_id < start_seq_id:
            raise ValueError(
                "CDR_MUTATION_RANGE_INVALID: end index must be greater than or equal to start"
            )
        if (end_seq_id - start_seq_id + 1) > _MAX_RANGE_SPAN:
            raise ValueError(
                "CDR_MUTATION_RANGE_INVALID: requested range exceeds maximum supported span"
            )

        return CDRMutationSpec(
            chain_id=chain_id,
            start_seq_id=start_seq_id,
            end_seq_id=end_seq_id,
            insertion_code="",
            from_residue=None,
            to_residue=to_residue,
            mode="range_substitution",
        )

    match = _POINT_MUTATION_RE.match(candidate)
    if match is None:
        raise ValueError(
            "CDR_MUTATION_SPEC_INVALID_FORMAT: expected CHAIN:SEQ[ICODE]:FROM>TO"
        )

    chain_id = match.group("chain")
    seq_id = int(match.group("seq_id"))
    insertion_code = match.group("icode")
    from_residue = match.group("from")
    to_residue = match.group("to")

    return CDRMutationSpec(
        chain_id=chain_id,
        start_seq_id=seq_id,
        end_seq_id=seq_id,
        insertion_code=insertion_code,
        from_residue=from_residue,
        to_residue=to_residue,
        mode="point_substitution",
    )


def run_cdr_mutation_stress_batch(specs: list[str]) -> CDRStressBatchSummary:
    """Run parser-only stress harness over a list of mutation specs.

    This Phase 6 scaffold intentionally validates and summarizes parser outcomes only.
    It is not wired into the default prediction path.
    """

    results: list[CDRStressCaseResult] = []
    for raw_spec in specs:
        try:
            parsed = parse_cdr_mutation_spec(raw_spec)
            results.append(
                CDRStressCaseResult(
                    input_spec=raw_spec,
                    status="parsed",
                    parsed_spec=parsed,
                )
            )
        except ValueError as exc:
            results.append(
                CDRStressCaseResult(
                    input_spec=raw_spec,
                    status="failed",
                    error=str(exc),
                )
            )

    parsed_count = sum(1 for result in results if result.status == "parsed")
    failed_count = len(results) - parsed_count
    return CDRStressBatchSummary(
        total_specs=len(results),
        parsed_specs=parsed_count,
        failed_specs=failed_count,
        results=results,
    )
