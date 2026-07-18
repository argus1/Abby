from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from typing import Any, Literal

from abby_api.services.cdr_annotation import annotate_cdr_h3

_POINT_MUTATION_RE = re.compile(
    r"^(?P<chain>[A-Za-z0-9]+):(?P<seq_id>\d+)(?P<icode>[A-Za-z]?):"
    r"(?P<from>[A-Z])>(?P<to>[A-Z])$"
)
_RANGE_MUTATION_RE = re.compile(
    r"^(?P<chain>[A-Za-z0-9]+):(?P<start>\d+)-(?P<end>\d+):(?P<to>[A-Z])$"
)
_MAX_RANGE_SPAN = 64
_ONE_TO_THREE = {
    "A": "ALA",
    "R": "ARG",
    "N": "ASN",
    "D": "ASP",
    "C": "CYS",
    "Q": "GLN",
    "E": "GLU",
    "G": "GLY",
    "H": "HIS",
    "I": "ILE",
    "L": "LEU",
    "K": "LYS",
    "M": "MET",
    "F": "PHE",
    "P": "PRO",
    "S": "SER",
    "T": "THR",
    "W": "TRP",
    "Y": "TYR",
    "V": "VAL",
}
_THREE_TO_ONE = {value: key for key, value in _ONE_TO_THREE.items()}


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


def _iter_residues(structure: Any):
    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return
    for chain in models[0].get_chains():
        chain_id = str(getattr(chain, "id", "")).strip()
        if not chain_id:
            continue
        for residue in chain.get_residues():
            yield chain_id, residue


def _mutate_residue_name(residue: Any, new_resname: str) -> bool:
    if hasattr(residue, "resname"):
        setattr(residue, "resname", new_resname)
        return True
    if hasattr(residue, "_residue_name"):
        setattr(residue, "_residue_name", new_resname)
        return True
    if hasattr(residue, "_resname"):
        setattr(residue, "_resname", new_resname)
        return True
    return False


def _apply_point_mutation(structure: Any, spec: CDRMutationSpec) -> bool:
    target_resname = _ONE_TO_THREE.get(spec.to_residue)
    if target_resname is None:
        return False

    for chain_id, residue in _iter_residues(structure):
        if chain_id != spec.chain_id:
            continue
        residue_id = getattr(residue, "id", None)
        if not isinstance(residue_id, tuple) or len(residue_id) < 3:
            continue
        if residue_id[0] != " ":
            continue
        try:
            sequence_id = int(residue_id[1])
        except (TypeError, ValueError):
            continue
        insertion_code = str(residue_id[2] or "").strip()
        if insertion_code in {"?", "."}:
            insertion_code = ""

        if sequence_id != spec.start_seq_id:
            continue
        if insertion_code != spec.insertion_code:
            continue

        if hasattr(residue, "get_resname"):
            current_three = residue.get_resname()
        else:
            current_three = getattr(residue, "resname", "")
        current_one = _THREE_TO_ONE.get(str(current_three).strip().upper())
        if spec.from_residue is not None and current_one != spec.from_residue:
            return False
        return _mutate_residue_name(residue, target_resname)

    return False


def _apply_range_mutation(structure: Any, spec: CDRMutationSpec) -> bool:
    target_resname = _ONE_TO_THREE.get(spec.to_residue)
    if target_resname is None:
        return False

    changed = 0
    for chain_id, residue in _iter_residues(structure):
        if chain_id != spec.chain_id:
            continue
        residue_id = getattr(residue, "id", None)
        if not isinstance(residue_id, tuple) or len(residue_id) < 3:
            continue
        if residue_id[0] != " ":
            continue
        try:
            sequence_id = int(residue_id[1])
        except (TypeError, ValueError):
            continue
        if spec.start_seq_id <= sequence_id <= spec.end_seq_id:
            if _mutate_residue_name(residue, target_resname):
                changed += 1

    return changed > 0


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


def run_cdr_mutation_annotation_probe(
    structure: Any,
    *,
    mutation_specs: list[str],
) -> dict[str, Any]:
    """Apply point mutations and probe CDR annotation resilience deterministically."""

    mutated_structure = copy.deepcopy(structure)
    applied_mutation_count = 0
    failed_mutation_count = 0
    issues: list[dict[str, str]] = []
    for raw_spec in mutation_specs:
        try:
            parsed_spec = parse_cdr_mutation_spec(raw_spec)
        except ValueError as exc:
            failed_mutation_count += 1
            code = str(exc).split(":", 1)[0].strip() or "CDR_MUTATION_SPEC_INVALID"
            issues.append(
                {
                    "code": code,
                    "message": str(exc),
                    "spec": raw_spec,
                }
            )
            continue

        apply_ok = False
        if parsed_spec.mode == "point_substitution":
            apply_ok = _apply_point_mutation(mutated_structure, parsed_spec)
        elif parsed_spec.mode == "range_substitution":
            apply_ok = _apply_range_mutation(mutated_structure, parsed_spec)
        else:
            failed_mutation_count += 1
            issues.append(
                {
                    "code": "CDR_MUTATION_MODE_UNSUPPORTED",
                    "message": "Mutation probe encountered unsupported mutation mode",
                    "spec": raw_spec,
                }
            )
            continue

        if apply_ok:
            applied_mutation_count += 1
        else:
            failed_mutation_count += 1
            issues.append(
                {
                    "code": "CDR_MUTATION_APPLY_FAILED",
                    "message": (
                        "Mutation target could not be applied (missing chain/residue or source "
                        "residue mismatch)"
                    ),
                    "spec": raw_spec,
                }
            )

    first = annotate_cdr_h3(mutated_structure)
    second = annotate_cdr_h3(mutated_structure)
    return {
        "status": "completed" if applied_mutation_count > 0 else "failed",
        "applied_mutation_count": applied_mutation_count,
        "failed_mutation_count": failed_mutation_count,
        "deterministic": first == second,
        "issues": issues,
        "annotation": first,
    }
