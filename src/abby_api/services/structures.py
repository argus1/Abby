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

_CDR_VALIDATION_CODES = {
    "CDR_CHAIN_ROLE_AMBIGUOUS",
    "CDR_BOUNDARY_AMBIGUOUS",
    "CDR_MOTIF_FALLBACK_USED",
    "CDR_NUMBERING_MISSING",
    "CDR_BASELINE_DRIFT_FLAGGED",
}

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"
MD_CANONICAL_CHAIN_IDS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopqrstuvwxyz")


def _normalize_format(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".mmcif") or lowered.endswith(".cif"):
        return "mmcif"
    if lowered.endswith(".pdb"):
        return "pdb"
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported structure format."
    )


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
            prediction_mode=mode,
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
    warning_details = [
        issue for issue in summary.warning_details if issue.code not in _CDR_VALIDATION_CODES
    ]
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


def _build_cdr_validation_issues(summary: StructureSummary) -> list[StructureValidationIssue]:
    cdr_annotation = summary.metadata.get("cdr_annotation", {})
    if not isinstance(cdr_annotation, dict):
        return []

    warnings = cdr_annotation.get("warnings", [])
    if not isinstance(warnings, list):
        return []

    selected_heavy_chain = cdr_annotation.get("selected_heavy_chain")
    scheme = cdr_annotation.get("scheme")
    boundary_source = cdr_annotation.get("boundary_source")
    boundary_confidence = cdr_annotation.get("boundary_confidence")
    chains_payload = cdr_annotation.get("chains", {})
    quality_baseline = cdr_annotation.get("quality_baseline", {})
    if not isinstance(chains_payload, dict):
        chains_payload = {}
    if not isinstance(quality_baseline, dict):
        quality_baseline = {}

    details_payload = {
        "cdr_annotation_available": bool(cdr_annotation.get("available", False)),
        "antibody_format": cdr_annotation.get(
            "antibody_format",
            "unknown_antibody_format",
        ),
        "selected_heavy_chain": selected_heavy_chain,
        "scheme": scheme,
        "boundary_source": boundary_source,
        "boundary_confidence": boundary_confidence,
        "chains": chains_payload,
        "region_applicability": cdr_annotation.get("region_applicability", {}),
        "quality_baseline": quality_baseline,
    }

    issue_messages = {
        "CDR_CHAIN_ROLE_AMBIGUOUS": (
            "CDR validation could not assign antibody chain roles with high confidence."
        ),
        "CDR_BOUNDARY_AMBIGUOUS": (
            "CDR validation detected partial or ambiguous region boundaries for one or more chains."
        ),
        "CDR_MOTIF_FALLBACK_USED": (
            "CDR validation used motif fallback because numbering-derived "
            "boundaries were unavailable."
        ),
        "CDR_NUMBERING_MISSING": (
            "CDR validation could not find complete numbering-derived "
            "boundaries for one or more chains."
        ),
    }

    issues: list[StructureValidationIssue] = []
    for warning_code in warnings:
        code = str(warning_code).strip()
        if code not in _CDR_VALIDATION_CODES:
            continue
        issues.append(
            StructureValidationIssue(
                code=code,
                message=issue_messages.get(code, "CDR validation reported a typed issue."),
                details=details_payload,
            )
        )

    drift_flag = bool(quality_baseline.get("drift_flag", False))
    drift_reason_codes = quality_baseline.get("drift_reason_codes", [])
    if not isinstance(drift_reason_codes, list):
        drift_reason_codes = []
    if drift_flag:
        issues.append(
            StructureValidationIssue(
                code="CDR_BASELINE_DRIFT_FLAGGED",
                message=(
                    "CDR QA baseline flagged potential confidence drift; review drift reasons "
                    "for fallback, ambiguity, or incomplete boundary signals."
                ),
                details={
                    **details_payload,
                    "drift_reason_codes": [str(code) for code in drift_reason_codes],
                },
            )
        )
    return issues


def _build_aptamer_validation_errors(
    summary: StructureSummary,
    chains: ChainMapping,
) -> list[StructureValidationIssue]:
    profile = summary.metadata.get("nucleic_acid_profile", {})
    if not isinstance(profile, dict):
        profile = {}
    chain_types = profile.get("chain_types", {})
    if not isinstance(chain_types, dict):
        chain_types = {}

    partner_1_chain_types = {
        chain_id: str(chain_types.get(chain_id, "unknown")) for chain_id in chains.partner_1
    }
    issues: list[StructureValidationIssue] = []
    nucleic_acid_types = {"dna", "rna", "mixed"}
    if not any(
        chain_type in nucleic_acid_types for chain_type in partner_1_chain_types.values()
    ):
        issues.append(
            StructureValidationIssue(
                code="APTAMER_CHAIN_REQUIRED",
                message="Aptamer mode requires a DNA or RNA chain in partner_1.",
                details={
                    "selected_partner_1_chains": chains.partner_1,
                    "partner_1_chain_types": partner_1_chain_types,
                },
            )
        )

    partner_2_chain_types = {
        chain_id: str(chain_types.get(chain_id, "unknown")) for chain_id in chains.partner_2
    }
    if not any(
        chain_type not in nucleic_acid_types
        for chain_type in partner_2_chain_types.values()
    ):
        issues.append(
            StructureValidationIssue(
                code="APTAMER_TARGET_CHAIN_REQUIRED",
                message=(
                    "Aptamer mode requires a non-nucleic-acid target chain in partner_2."
                ),
                details={
                    "selected_partner_2_chains": chains.partner_2,
                    "partner_2_chain_types": partner_2_chain_types,
                },
            )
        )
    return issues


def _build_aptamer_validation_warnings(
    summary: StructureSummary,
) -> list[StructureValidationIssue]:
    profile = summary.metadata.get("nucleic_acid_profile", {})
    if not isinstance(profile, dict):
        return []
    issues: list[StructureValidationIssue] = []
    modified_nucleotides = profile.get("modified_nucleotides", [])
    if isinstance(modified_nucleotides, list) and modified_nucleotides:
        issues.append(
            StructureValidationIssue(
                code="APTAMER_MODIFIED_NUCLEOTIDE",
                message=(
                    "Modified nucleotides require force-field and topology "
                    "parameterization review."
                ),
                details={"modified_nucleotides": modified_nucleotides},
            )
        )

    atom_naming_issues = profile.get("atom_naming_issues", [])
    if isinstance(atom_naming_issues, list) and atom_naming_issues:
        issues.append(
            StructureValidationIssue(
                code="APTAMER_ATOM_NAMING_INCOMPATIBLE",
                message=(
                    "Nucleotide atoms use legacy naming that may be incompatible "
                    "with topology generation."
                ),
                details={"atom_naming_issues": atom_naming_issues},
            )
        )

    residue_naming_issues = profile.get("residue_naming_issues", [])
    if isinstance(residue_naming_issues, list) and residue_naming_issues:
        issues.append(
            StructureValidationIssue(
                code="APTAMER_RESIDUE_NAMING_INCOMPATIBLE",
                message=(
                    "Nucleotide residues use legacy names that may be incompatible "
                    "with topology generation."
                ),
                details={"residue_naming_issues": residue_naming_issues},
            )
        )

    chain_types = profile.get("chain_types", {})
    if isinstance(chain_types, dict):
        mixed_chain_ids = sorted(
            str(chain_id)
            for chain_id, chain_type in chain_types.items()
            if chain_type == "mixed"
        )
        if mixed_chain_ids:
            issues.append(
                StructureValidationIssue(
                    code="APTAMER_MIXED_DNA_RNA_CHAIN",
                    message=(
                        "A nucleic-acid chain contains both DNA and RNA residue naming."
                    ),
                    details={"mixed_chain_ids": mixed_chain_ids},
                )
            )
    return issues


def build_md_handoff_plan(chains: ChainMapping) -> dict[str, object]:
    selected_chains = [*chains.partner_1, *chains.partner_2]
    capacity_ok = len(selected_chains) <= len(MD_CANONICAL_CHAIN_IDS)
    canonical_chain_map: dict[str, str] = {}
    canonical_ids = MD_CANONICAL_CHAIN_IDS[: len(selected_chains)]

    for index, chain_id in enumerate(selected_chains):
        if index < len(canonical_ids):
            canonical_chain_map[chain_id] = canonical_ids[index]

    renaming_required = any(
        canonical_chain_map.get(chain_id) != chain_id for chain_id in selected_chains
    )
    source_chain_ids_noncanonical = sorted(
        {
            chain_id
            for chain_id in selected_chains
            if len(chain_id) != 1
            or (not chain_id.isalnum())
            or (chain_id.isalpha() and chain_id != chain_id.upper())
        }
    )

    issues: list[dict[str, object]] = []
    if not capacity_ok:
        issues.append(
            {
                "code": "CHAIN_ID_CAPACITY_EXCEEDED",
                "message": (
                    "Selected chains exceed supported canonical chain ID "
                    "capacity for MD handoff."
                ),
                "details": {
                    "selected_chain_count": len(selected_chains),
                    "supported_capacity": len(MD_CANONICAL_CHAIN_IDS),
                },
            }
        )
    if renaming_required:
        issues.append(
            {
                "code": "CHAIN_CANONICALIZATION_REQUIRED",
                "message": (
                    "Selected chains require remapping to canonical "
                    "single-character IDs for MD handoff."
                ),
                "details": {"canonical_chain_map": canonical_chain_map},
            }
        )
    if source_chain_ids_noncanonical:
        issues.append(
            {
                "code": "SOURCE_CHAIN_IDS_NONCANONICAL",
                "message": (
                    "One or more source chain IDs are non-canonical for "
                    "pdb2gmx style workflows."
                ),
                "details": {"source_chain_ids_noncanonical": source_chain_ids_noncanonical},
            }
        )

    return {
        "selected_chains": selected_chains,
        "capacity_ok": capacity_ok,
        "renaming_required": renaming_required,
        "source_chain_ids_noncanonical": source_chain_ids_noncanonical,
        "canonical_chain_map": canonical_chain_map,
        "canonical_partner_1": [
            canonical_chain_map.get(chain_id, "") for chain_id in chains.partner_1
        ],
        "canonical_partner_2": [
            canonical_chain_map.get(chain_id, "") for chain_id in chains.partner_2
        ],
        "issues": issues,
        "ready_for_md_handoff": capacity_ok,
    }


def summarize_structure_detail(structure_id: UUID) -> StructureSummary:
    detail = get_structure(structure_id)
    if detail is None or detail.summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Structure summary not found."
        )
    return detail.summary


def validate_structure(request: StructureValidationRequest) -> StructureValidationResult:
    detail = get_structure(request.structure_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found.")
    if detail.summary is None:
        file_path = get_structure_file(request.structure_id)
        if file_path is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Structure file not found."
            )
        normalized_format = "mmcif" if detail.format in {"mmcif", "cif"} else "pdb"
        parsed_structure, parser_name = parse_structure_file(file_path, normalized_format)
        set_structure_summary(
            request.structure_id,
            summarize_structure(
                parsed_structure,
                parser_name,
                file_path=file_path,
                format_name=normalized_format,
                prediction_mode=detail.mode,
            ),
        )
        detail = get_structure(request.structure_id)
        if detail is None or detail.summary is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Unable to summarize structure.",
            )

    normalized_groups = normalize_chain_groups(request.chains)
    warnings, errors, partner_residue_counts, warning_details, error_details = (
        validate_partner_mapping(
            detail.summary,
            normalized_groups,
        )
    )
    if request.mode != detail.mode:
        errors.append("PREDICTION_MODE_MISMATCH")
        error_details.append(
            StructureValidationIssue(
                code="PREDICTION_MODE_MISMATCH",
                message="Validation mode must match the structure upload mode.",
                details={
                    "structure_mode": detail.mode,
                    "requested_mode": request.mode,
                },
            )
        )
    md_handoff = build_md_handoff_plan(normalized_groups)
    if md_handoff["issues"]:
        warnings.append("MD_CHAIN_CANONICALIZATION_SUGGESTED")
        warning_details.append(
            StructureValidationIssue(
                code="MD_CHAIN_CANONICALIZATION_SUGGESTED",
                message=(
                    "MD handoff chain canonicalization guidance is available "
                    "for selected chains."
                ),
                details={"md_handoff": md_handoff},
            )
        )

    cdr_warning_details = _build_cdr_validation_issues(detail.summary)
    warning_details.extend(cdr_warning_details)
    warnings.extend(issue.code for issue in cdr_warning_details)

    if request.mode == "aptamer_target":
        aptamer_error_details = _build_aptamer_validation_errors(
            detail.summary,
            normalized_groups,
        )
        error_details.extend(aptamer_error_details)
        errors.extend(issue.code for issue in aptamer_error_details)
        aptamer_warning_details = _build_aptamer_validation_warnings(detail.summary)
        warning_details.extend(aptamer_warning_details)
        warnings.extend(issue.code for issue in aptamer_warning_details)

    normalized = "mmcif" if detail.format in {"mmcif", "cif"} else "pdb"
    inferred_roles = (
        {"partner_1": "aptamer", "partner_2": "target"}
        if request.mode == "aptamer_target"
        else {"partner_1": "receptor", "partner_2": "ligand"}
    )
    cdr_annotation = detail.summary.metadata.get("cdr_annotation", {})
    if isinstance(cdr_annotation, dict):
        antibody_format = cdr_annotation.get("antibody_format")
        if antibody_format is not None:
            inferred_roles["antibody_format"] = str(antibody_format)
    result = StructureValidationResult(
        valid=not errors,
        normalized_format=normalized,
        inferred_roles=inferred_roles,
        available_chains=detail.summary.available_chains,
        model_count=detail.summary.model_count,
        chain_groups=normalized_groups,
        partner_residue_counts=partner_residue_counts,
        warnings=sorted(set(warnings)),
        warning_details=warning_details,
        errors=errors,
        error_details=error_details,
        md_handoff=md_handoff,
    )
    set_validation(request.structure_id, result)
    detail.chains = normalized_groups
    return result


def get_structure_detail(structure_id: UUID) -> StructureDetail:
    detail = get_structure(structure_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Structure not found.")
    return detail
