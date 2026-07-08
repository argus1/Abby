from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from abby_api.repositories.memory import (
    get_structure,
    get_structure_file,
    save_structure,
    set_structure_summary,
    set_validation,
)
from abby_api.schemas.common import PredictionMode
from abby_api.schemas.structures import (
    ChainMapping,
    StructureDetail,
    StructureInput,
    StructureSummary,
    StructureValidationIssue,
    StructureValidationRequest,
    StructureValidationResult,
)
from abby_api.services.structure_parsing import parse_structure_file, summarize_structure

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"


def _normalize_format(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".mmcif") or lowered.endswith(".cif"):
        return "mmcif"
    if lowered.endswith(".pdb"):
        return "pdb"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported structure format.")


async def upload_structure(file: UploadFile, mode: PredictionMode) -> StructureInput:
    payload = await file.read()
    format_name = _normalize_format(file.filename or "")
    structure_id = uuid4()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOAD_DIR / f"{structure_id}_{file.filename or 'uploaded-structure'}"
    destination.write_bytes(payload)

    try:
        parsed_structure, parser_name = parse_structure_file(destination, format_name)
        summary = summarize_structure(
            parsed_structure,
            parser_name,
            file_path=destination,
            format_name=format_name,
        )
    except Exception as exc:  # pragma: no cover - defensive error surface
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unable to parse structure file: {exc}",
        ) from exc

    structure = StructureInput(
        structure_id=structure_id,
        format="mmcif" if format_name == "mmcif" else "pdb",
        source="upload",
        filename=file.filename or "uploaded-structure",
        sha256=sha256(payload).hexdigest(),
        mode=mode,
        chains=None,
    )
    save_structure(structure, file_path=destination, summary=summary)
    return structure


def normalize_chain_groups(chains: ChainMapping) -> ChainMapping:
    partner_1 = sorted({chain.strip() for chain in chains.partner_1 if chain.strip()})
    partner_2 = sorted({chain.strip() for chain in chains.partner_2 if chain.strip()})
    return ChainMapping(partner_1=partner_1, partner_2=partner_2)


def validate_partner_mapping(
    summary: StructureSummary,
    chains: ChainMapping,
) -> tuple[
    list[str],
    list[str],
    dict[str, int],
    list[StructureValidationIssue],
    list[StructureValidationIssue],
]:
    warnings = list(summary.warnings)
    warning_details = list(summary.warning_details)
    errors: list[str] = []
    error_details: list[StructureValidationIssue] = []
    normalized = normalize_chain_groups(chains)

    if not normalized.partner_1 or not normalized.partner_2:
        errors.append("EMPTY_PARTNER_SELECTION")
        error_details.append(
            StructureValidationIssue(
                code="EMPTY_PARTNER_SELECTION",
                message="Both partner groups must contain at least one chain.",
                details={
                    "partner_1_count": len(normalized.partner_1),
                    "partner_2_count": len(normalized.partner_2),
                },
            )
        )

    overlap = set(normalized.partner_1) & set(normalized.partner_2)
    if overlap:
        errors.append("CHAIN_GROUP_OVERLAP")
        error_details.append(
            StructureValidationIssue(
                code="CHAIN_GROUP_OVERLAP",
                message="A chain cannot belong to both partner groups.",
                details={"overlap": sorted(overlap)},
            )
        )

    missing = [
        chain
        for chain in [*normalized.partner_1, *normalized.partner_2]
        if chain not in summary.available_chains
    ]
    if missing:
        errors.append("UNKNOWN_CHAIN_SELECTION")
        error_details.append(
            StructureValidationIssue(
                code="UNKNOWN_CHAIN_SELECTION",
                message="One or more selected chains are not present in the parsed structure.",
                details={
                    "missing_chains": sorted(set(missing)),
                    "available_chains": summary.available_chains,
                },
            )
        )

    partner_residue_counts = {
        "partner_1": sum(summary.residue_counts.get(chain, 0) for chain in normalized.partner_1),
        "partner_2": sum(summary.residue_counts.get(chain, 0) for chain in normalized.partner_2),
    }
    return warnings, errors, partner_residue_counts, warning_details, error_details


def summarize_structure_detail(structure_id: UUID) -> StructureSummary:
    detail = get_structure(structure_id)
    if detail is None or detail.summary is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure summary not found.")
    return detail.summary


def validate_structure(request: StructureValidationRequest) -> StructureValidationResult:
    detail = get_structure(request.structure_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found.")
    if detail.summary is None:
        file_path = get_structure_file(request.structure_id)
        if file_path is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure file not found.")
        normalized_format = "mmcif" if detail.format in {"mmcif", "cif"} else "pdb"
        parsed_structure, parser_name = parse_structure_file(file_path, normalized_format)
        set_structure_summary(
            request.structure_id,
            summarize_structure(
                parsed_structure,
                parser_name,
                file_path=file_path,
                format_name=normalized_format,
            ),
        )
        detail = get_structure(request.structure_id)
        if detail is None or detail.summary is None:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unable to summarize structure.")

    normalized_groups = normalize_chain_groups(request.chains)
    warnings, errors, partner_residue_counts, warning_details, error_details = validate_partner_mapping(
        detail.summary,
        normalized_groups,
    )
    normalized = "mmcif" if detail.format in {"mmcif", "cif"} else "pdb"
    result = StructureValidationResult(
        valid=not errors,
        normalized_format=normalized,
        inferred_roles={"partner_1": "receptor", "partner_2": "ligand"},
        available_chains=detail.summary.available_chains,
        model_count=detail.summary.model_count,
        chain_groups=normalized_groups,
        partner_residue_counts=partner_residue_counts,
        warnings=warnings,
        warning_details=warning_details,
        errors=errors,
        error_details=error_details,
    )
    set_validation(request.structure_id, result)
    detail.chains = normalized_groups
    return result


def get_structure_detail(structure_id: UUID) -> StructureDetail:
    detail = get_structure(structure_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found.")
    return detail
