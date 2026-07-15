from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

CDR_REGION_NAMES: tuple[str, ...] = (
    "CDR-H1",
    "CDR-H2",
    "CDR-H3",
    "CDR-L1",
    "CDR-L2",
    "CDR-L3",
)

CDR_REGION_GLOSSARY: dict[str, str] = {
    "CDR-H1": "Heavy-chain complementarity-determining region 1.",
    "CDR-H2": "Heavy-chain complementarity-determining region 2.",
    "CDR-H3": "Heavy-chain complementarity-determining region 3.",
    "CDR-L1": "Light-chain complementarity-determining region 1.",
    "CDR-L2": "Light-chain complementarity-determining region 2.",
    "CDR-L3": "Light-chain complementarity-determining region 3.",
}

CDR_RESIDUE_KEY_FORMAT = "(chain_id, auth_seq_id/label_seq_id, insertion_code)"

CDR_CHAIN_ROLE_AMBIGUOUS = "CDR_CHAIN_ROLE_AMBIGUOUS"
CDR_BOUNDARY_AMBIGUOUS = "CDR_BOUNDARY_AMBIGUOUS"
CDR_MOTIF_FALLBACK_USED = "CDR_MOTIF_FALLBACK_USED"
CDR_NUMBERING_MISSING = "CDR_NUMBERING_MISSING"

CDR_WARNING_ERROR_CODES: tuple[str, ...] = (
    CDR_CHAIN_ROLE_AMBIGUOUS,
    CDR_BOUNDARY_AMBIGUOUS,
    CDR_MOTIF_FALLBACK_USED,
    CDR_NUMBERING_MISSING,
)

CDRNumberingScheme = Literal["imgt", "kabat", "chothia", "aho", "motif_fallback"]
CDRBoundarySource = Literal["numbered", "motif_fallback", "hybrid"]
CDRBoundaryConfidence = Literal["high", "medium", "low"]


@dataclass(frozen=True, slots=True)
class _ChainResidue:
    chain_id: str
    sequence_id: int
    insertion_code: str
    residue_name: str


@dataclass(frozen=True, slots=True)
class _CDRWindow:
    scheme: CDRNumberingScheme
    source: CDRBoundarySource
    confidence: CDRBoundaryConfidence
    start_index: int
    end_index: int


_ONE_LETTER_RESIDUE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}

_H3_MOTIF = re.compile(r"C([A-Z]{4,30}?)WG[A-Z]G")

_CDR_BASELINE_FEATURE_SCHEMA_VERSION = "cdr_boundary_quality_features_v1"
_CDR_BASELINE_FEATURE_NAMES: tuple[str, ...] = (
    "available_flag",
    "numbering_source_flag",
    "motif_fallback_flag",
    "heavy_completeness_score",
    "selected_heavy_region_count",
    "warning_count",
    "heavy_candidate_margin",
    "motif_match_count",
)
_CDR_BASELINE_MODEL_CONTRACT: dict[str, Any] = {
    "model_id": "cdr_boundary_quality_heuristic",
    "model_version": "1.0.0",
    "contract_version": "cdr_boundary_quality_contract_v1",
    "model_family": "heuristic_baseline",
    "intended_use": "qa_drift_monitoring_only",
    "non_blocking": True,
    "feature_schema_version": _CDR_BASELINE_FEATURE_SCHEMA_VERSION,
    "supported_prediction_modes": ["antibody_antigen"],
    "output_schema_version": "cdr_boundary_quality_output_v1",
    "calibration_scaffold_version": "cdr_boundary_quality_calibration_scaffold_v1",
    "calibration_target_label": "observed_boundary_quality_pass",
    "calibration_metrics_supported": ["ece", "mce", "brier", "auc_roc"],
}

_HEAVY_REGION_WINDOWS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "kabat": (
        ("CDR-H1", 31, 35),
        ("CDR-H2", 50, 65),
        ("CDR-H3", 95, 102),
    ),
    "imgt": (
        ("CDR-H1", 27, 38),
        ("CDR-H2", 56, 65),
        ("CDR-H3", 105, 117),
    ),
}

_LIGHT_REGION_WINDOWS: dict[str, tuple[tuple[str, int, int], ...]] = {
    "kabat": (
        ("CDR-L1", 24, 34),
        ("CDR-L2", 50, 56),
        ("CDR-L3", 89, 97),
    ),
    "imgt": (
        ("CDR-L1", 27, 38),
        ("CDR-L2", 56, 65),
        ("CDR-L3", 105, 117),
    ),
}


def _chain_residues_from_structure(structure: Any) -> dict[str, list[_ChainResidue]]:
    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        return {}

    residues_by_chain: dict[str, list[_ChainResidue]] = {}
    for chain in models[0].get_chains():
        chain_id = str(getattr(chain, "id", "")).strip()
        if not chain_id:
            continue

        residues: list[_ChainResidue] = []
        for residue in chain.get_residues():
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

            residue_name = (
                residue.get_resname() if hasattr(residue, "get_resname") else "UNK"
            )
            residues.append(
                _ChainResidue(
                    chain_id=chain_id,
                    sequence_id=sequence_id,
                    insertion_code=insertion_code,
                    residue_name=str(residue_name).strip().upper(),
                )
            )

        residues_by_chain[chain_id] = sorted(
            residues,
            key=lambda item: (item.sequence_id, item.insertion_code),
        )

    return residues_by_chain


def _to_chain_sequence(residues: list[_ChainResidue]) -> str:
    return "".join(_ONE_LETTER_RESIDUE.get(residue.residue_name, "X") for residue in residues)


def _motif_matches(sequence: str) -> list[tuple[int, int]]:
    matches: list[tuple[int, int]] = []
    for match in _H3_MOTIF.finditer(sequence):
        start = int(match.start(1))
        end = int(match.end(1)) - 1
        if start <= end:
            matches.append((start, end))
    return matches


def _heavy_chain_score(
    chain_id: str,
    residues: list[_ChainResidue],
) -> tuple[int, list[tuple[int, int]]]:
    sequence = _to_chain_sequence(residues)
    motif_windows = _motif_matches(sequence)

    score = 0
    if len(sequence) >= 90:
        score += 2
    if "C" in sequence:
        score += 1
    if "W" in sequence:
        score += 1
    if motif_windows:
        score += 3

    normalized_chain_id = chain_id.strip().upper()
    if normalized_chain_id in {"H", "VH", "HEAVY"} or normalized_chain_id.startswith("H"):
        score += 1

    return score, motif_windows


def _infer_light_role(
    chain_id: str,
    residues: list[_ChainResidue],
) -> tuple[str, CDRBoundaryConfidence]:
    sequence = _to_chain_sequence(residues)
    normalized_chain_id = chain_id.strip().upper()

    has_light_length = 80 <= len(sequence) <= 140
    has_backbone_markers = "C" in sequence and ("F" in sequence or "W" in sequence)

    if not has_light_length and not has_backbone_markers:
        return "unknown", "low"

    if (
        "KAPPA" in normalized_chain_id
        or normalized_chain_id.startswith("VK")
        or normalized_chain_id.startswith("K")
    ):
        return "light_kappa", "medium"

    if (
        "LAMBDA" in normalized_chain_id
        or normalized_chain_id.startswith("VL")
        or normalized_chain_id.startswith("LAM")
        or normalized_chain_id.endswith("_L")
    ):
        return "light_lambda", "medium"

    if (
        normalized_chain_id in {"L", "LIGHT"}
        or normalized_chain_id.startswith("L")
        or has_light_length
    ):
        return "light_unknown", "medium"

    return "unknown", "low"


def _numbering_h3_window(residues: list[_ChainResidue]) -> _CDRWindow | None:
    # Prefer Kabat-like H3 window when available, then IMGT-like fallback.
    kabat = [
        index for index, residue in enumerate(residues) if 95 <= residue.sequence_id <= 102
    ]
    if len(kabat) >= 4:
        return _CDRWindow(
            scheme="kabat",
            source="numbered",
            confidence="high",
            start_index=min(kabat),
            end_index=max(kabat),
        )

    imgt = [index for index, residue in enumerate(residues) if 105 <= residue.sequence_id <= 117]
    if len(imgt) >= 5:
        return _CDRWindow(
            scheme="imgt",
            source="numbered",
            confidence="high",
            start_index=min(imgt),
            end_index=max(imgt),
        )
    return None


def _motif_h3_window(
    residues: list[_ChainResidue],
    motif_windows: list[tuple[int, int]],
) -> _CDRWindow | None:
    if len(motif_windows) != 1:
        return None
    start, end = motif_windows[0]
    if start < 0 or end >= len(residues):
        return None

    loop_length = (end - start) + 1
    confidence: CDRBoundaryConfidence = "medium" if 6 <= loop_length <= 20 else "low"
    return _CDRWindow(
        scheme="motif_fallback",
        source="motif_fallback",
        confidence=confidence,
        start_index=start,
        end_index=end,
    )


def _residue_key_payload(residue: _ChainResidue) -> dict[str, str]:
    return {
        "chain_id": residue.chain_id,
        "sequence_id": str(residue.sequence_id),
        "insertion_code": residue.insertion_code,
    }


def _build_region_payload(
    residues: list[_ChainResidue],
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    selected = residues[start_index : end_index + 1]
    return {
        "start_index": start_index,
        "end_index": end_index,
        "length": len(selected),
        "start_residue": _residue_key_payload(selected[0]),
        "end_residue": _residue_key_payload(selected[-1]),
        "residue_keys": [_residue_key_payload(residue) for residue in selected],
    }


def _extract_regions_by_windows(
    residues: list[_ChainResidue],
    region_windows: tuple[tuple[str, int, int], ...],
) -> dict[str, Any]:
    regions: dict[str, Any] = {}
    covered_residue_count = 0
    for region_name, start_seq_id, end_seq_id in region_windows:
        indices = [
            index
            for index, residue in enumerate(residues)
            if start_seq_id <= residue.sequence_id <= end_seq_id
        ]
        if not indices:
            continue
        start_index = min(indices)
        end_index = max(indices)
        region_payload = _build_region_payload(residues, start_index, end_index)
        regions[region_name] = region_payload
        covered_residue_count += int(region_payload["length"])

    return {
        "regions": regions,
        "region_count": len(regions),
        "covered_residue_count": covered_residue_count,
        "expected_region_count": len(region_windows),
    }


def _choose_best_numbered_extraction(
    residues: list[_ChainResidue],
    *,
    domain: Literal["heavy", "light"],
) -> dict[str, Any] | None:
    window_map = _HEAVY_REGION_WINDOWS if domain == "heavy" else _LIGHT_REGION_WINDOWS

    scheme_priority = {"kabat": 2, "imgt": 1}
    candidates: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for scheme, windows in window_map.items():
        extracted = _extract_regions_by_windows(residues, windows)
        candidates.append(
            (
                int(extracted["region_count"]),
                int(scheme_priority.get(scheme, 0)),
                int(extracted["covered_residue_count"]),
                scheme,
                extracted,
            )
        )

    if not candidates:
        return None

    best_region_count, _best_priority, _best_coverage, best_scheme, best_extracted = max(candidates)
    if best_region_count == 0:
        return None

    completeness = round(
        float(best_region_count) / max(float(best_extracted["expected_region_count"]), 1.0),
        4,
    )
    confidence: CDRBoundaryConfidence
    if best_region_count == best_extracted["expected_region_count"]:
        confidence = "high"
    elif best_region_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "scheme": best_scheme,
        "regions": best_extracted["regions"],
        "region_count": best_region_count,
        "expected_region_count": best_extracted["expected_region_count"],
        "completeness_score": completeness,
        "confidence": confidence,
    }


def _confidence_rank(confidence: CDRBoundaryConfidence | str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(str(confidence), 0)


def _classify_baseline_score(score: float) -> CDRBoundaryConfidence:
    if score >= 0.8:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _build_boundary_quality_baseline(
    *,
    available: bool,
    boundary_source: CDRBoundarySource | None,
    boundary_confidence: CDRBoundaryConfidence,
    selected_heavy_chain: str | None,
    chains_payload: dict[str, dict[str, Any]],
    warnings: list[str],
    heavy_scores: dict[str, int],
    motif_by_chain: dict[str, list[tuple[int, int]]],
    heavy_completeness_score: float,
) -> dict[str, Any]:
    warning_set = set(warnings)
    heavy_chain_payload = (
        chains_payload.get(selected_heavy_chain, {}) if selected_heavy_chain is not None else {}
    )
    heavy_region_count = len(heavy_chain_payload.get("regions", {}))
    sorted_scores = sorted(heavy_scores.values(), reverse=True)
    heavy_candidate_margin = (
        sorted_scores[0] - sorted_scores[1]
        if len(sorted_scores) > 1
        else (sorted_scores[0] if sorted_scores else 0)
    )
    motif_match_count = (
        len(motif_by_chain.get(selected_heavy_chain, [])) if selected_heavy_chain is not None else 0
    )

    feature_vector = {
        "available_flag": 1.0 if available else 0.0,
        "numbering_source_flag": 1.0 if boundary_source == "numbered" else 0.0,
        "motif_fallback_flag": (
            1.0 if boundary_source in {"motif_fallback", "hybrid"} else 0.0
        ),
        "heavy_completeness_score": round(float(heavy_completeness_score), 4),
        "selected_heavy_region_count": float(heavy_region_count),
        "warning_count": float(len(warning_set)),
        "heavy_candidate_margin": float(max(heavy_candidate_margin, 0)),
        "motif_match_count": float(motif_match_count),
    }
    feature_vector = {
        feature_name: float(feature_vector.get(feature_name, 0.0))
        for feature_name in _CDR_BASELINE_FEATURE_NAMES
    }

    score = 0.1
    if available:
        score += 0.2

    if boundary_source == "numbered":
        score += 0.35
    elif boundary_source == "hybrid":
        score += 0.18
    elif boundary_source == "motif_fallback":
        score += 0.08

    score += min(0.25, float(heavy_completeness_score) * 0.25)
    score += min(0.12, float(heavy_region_count) * 0.04)
    score += min(0.08, float(max(heavy_candidate_margin, 0)) * 0.04)

    if motif_match_count == 1:
        score += 0.05

    score -= min(0.16, float(len(warning_set)) * 0.04)
    if CDR_NUMBERING_MISSING in warning_set:
        score -= 0.12
    if CDR_MOTIF_FALLBACK_USED in warning_set:
        score -= 0.08
    if CDR_BOUNDARY_AMBIGUOUS in warning_set:
        score -= 0.2
    if CDR_CHAIN_ROLE_AMBIGUOUS in warning_set:
        score -= 0.12

    score = round(min(max(score, 0.0), 1.0), 4)
    predicted_confidence = _classify_baseline_score(score)

    drift_reason_codes: list[str] = []
    if not available:
        drift_reason_codes.append("ANNOTATION_UNAVAILABLE")
    if boundary_source in {"motif_fallback", "hybrid"}:
        drift_reason_codes.append("FALLBACK_BOUNDARY_SOURCE")
    if CDR_NUMBERING_MISSING in warning_set:
        drift_reason_codes.append("NUMBERING_SIGNAL_MISSING")
    if CDR_BOUNDARY_AMBIGUOUS in warning_set:
        drift_reason_codes.append("AMBIGUOUS_BOUNDARY_WARNING")
    if CDR_CHAIN_ROLE_AMBIGUOUS in warning_set:
        drift_reason_codes.append("AMBIGUOUS_CHAIN_ROLE_WARNING")
    if heavy_completeness_score < 1.0 and heavy_region_count > 0:
        drift_reason_codes.append("PARTIAL_REGION_COVERAGE")
    if _confidence_rank(predicted_confidence) < _confidence_rank(boundary_confidence):
        drift_reason_codes.append("BASELINE_LOWER_THAN_PRIMARY_CONFIDENCE")

    return {
        "available": True,
        "model_name": "heuristic_v1",
        "model_contract": dict(_CDR_BASELINE_MODEL_CONTRACT),
        "predicted_confidence_class": predicted_confidence,
        "primary_boundary_confidence": boundary_confidence,
        "score": score,
        "drift_flag": bool(drift_reason_codes),
        "drift_reason_codes": drift_reason_codes,
        "feature_vector": feature_vector,
    }


def annotate_cdr_h3(structure: Any) -> dict[str, Any]:
    """Annotate CDR-H3 boundaries using numbered windows first, motif fallback second."""

    residues_by_chain = _chain_residues_from_structure(structure)
    if not residues_by_chain:
        return {
            "available": False,
            "scheme": None,
            "boundary_source": None,
            "boundary_confidence": "low",
            "selected_heavy_chain": None,
            "chains": {},
            "warnings": [CDR_CHAIN_ROLE_AMBIGUOUS, CDR_BOUNDARY_AMBIGUOUS],
        }

    heavy_scores: dict[str, int] = {}
    motif_by_chain: dict[str, list[tuple[int, int]]] = {}
    for chain_id, residues in residues_by_chain.items():
        score, motif_windows = _heavy_chain_score(chain_id, residues)
        heavy_scores[chain_id] = score
        motif_by_chain[chain_id] = motif_windows

    highest_score = max(heavy_scores.values()) if heavy_scores else 0
    top_chains = sorted(
        [chain_id for chain_id, score in heavy_scores.items() if score == highest_score]
    )

    warnings: list[str] = []
    selected_heavy_chain = top_chains[0] if highest_score >= 2 and top_chains else None
    if highest_score >= 2 and len(top_chains) > 1:
        warnings.append(CDR_CHAIN_ROLE_AMBIGUOUS)

    annotation_window: _CDRWindow | None = None
    heavy_region_scheme: str | None = None
    heavy_regions: dict[str, Any] = {}
    heavy_completeness_score = 0.0
    heavy_confidence: CDRBoundaryConfidence = "low"
    boundary_source: CDRBoundarySource | None = None

    if selected_heavy_chain is not None:
        residues = residues_by_chain[selected_heavy_chain]
        heavy_numbered = _choose_best_numbered_extraction(residues, domain="heavy")
        if heavy_numbered is not None:
            heavy_region_scheme = str(heavy_numbered["scheme"])
            heavy_regions = dict(heavy_numbered["regions"])
            heavy_completeness_score = float(heavy_numbered["completeness_score"])
            heavy_confidence = heavy_numbered["confidence"]
            if int(heavy_numbered["region_count"]) < int(heavy_numbered["expected_region_count"]):
                warnings.append(CDR_BOUNDARY_AMBIGUOUS)
            if "CDR-H3" in heavy_regions:
                heavy_confidence = "high"
                h3_payload = heavy_regions["CDR-H3"]
                annotation_window = _CDRWindow(
                    scheme=heavy_region_scheme,  # type: ignore[arg-type]
                    source="numbered",
                    confidence="high",
                    start_index=int(h3_payload["start_index"]),
                    end_index=int(h3_payload["end_index"]),
                )
                boundary_source = "numbered"

        if annotation_window is None:
            warnings.append(CDR_NUMBERING_MISSING)
            motif_windows = motif_by_chain[selected_heavy_chain]
            if len(motif_windows) > 1:
                warnings.append(CDR_BOUNDARY_AMBIGUOUS)
            fallback_window = _motif_h3_window(residues, motif_windows)
            annotation_window = fallback_window
            if fallback_window is not None:
                heavy_regions["CDR-H3"] = _build_region_payload(
                    residues,
                    fallback_window.start_index,
                    fallback_window.end_index,
                )
                heavy_completeness_score = max(heavy_completeness_score, round(1 / 3, 4))
                heavy_confidence = fallback_window.confidence
                if heavy_region_scheme is None:
                    heavy_region_scheme = fallback_window.scheme
                    boundary_source = "motif_fallback"
                else:
                    boundary_source = "hybrid"
            if annotation_window is not None:
                warnings.append(CDR_MOTIF_FALLBACK_USED)
    else:
        warnings.append(CDR_NUMBERING_MISSING)

    chains_payload: dict[str, dict[str, Any]] = {}
    for chain_id, residues in residues_by_chain.items():
        chain_scheme: str | None = None
        completeness_score = 0.0
        if chain_id == selected_heavy_chain:
            role = "heavy"
            confidence: CDRBoundaryConfidence = heavy_confidence
            chain_regions = dict(heavy_regions)
            chain_scheme = heavy_region_scheme
            completeness_score = heavy_completeness_score
        else:
            role, confidence = _infer_light_role(chain_id, residues)
            chain_regions: dict[str, Any] = {}
            if role.startswith("light"):
                light_numbered = _choose_best_numbered_extraction(residues, domain="light")
                if light_numbered is not None:
                    chain_scheme = str(light_numbered["scheme"])
                    chain_regions = dict(light_numbered["regions"])
                    completeness_score = float(light_numbered["completeness_score"])
                    if int(light_numbered["region_count"]) < int(
                        light_numbered["expected_region_count"]
                    ):
                        warnings.append(CDR_BOUNDARY_AMBIGUOUS)
                    if confidence == "medium" and light_numbered["confidence"] == "high":
                        confidence = "high"
                else:
                    warnings.append(CDR_NUMBERING_MISSING)
                    if confidence == "medium":
                        confidence = "low"

        chains_payload[chain_id] = {
            "role": role,
            "confidence": confidence,
            "scheme": chain_scheme,
            "completeness_score": completeness_score,
            "regions": chain_regions,
            "residue_count": len(residues),
        }

    available = annotation_window is not None

    deduped_warnings = sorted(set(warnings))
    quality_baseline = _build_boundary_quality_baseline(
        available=available,
        boundary_source=boundary_source,
        boundary_confidence=(
            annotation_window.confidence if annotation_window is not None else "low"
        ),
        selected_heavy_chain=selected_heavy_chain,
        chains_payload=chains_payload,
        warnings=deduped_warnings,
        heavy_scores=heavy_scores,
        motif_by_chain=motif_by_chain,
        heavy_completeness_score=heavy_completeness_score,
    )

    return {
        "available": available,
        "scheme": (
            annotation_window.scheme if annotation_window is not None else heavy_region_scheme
        ),
        "boundary_source": boundary_source,
        "boundary_confidence": (
            annotation_window.confidence if annotation_window is not None else "low"
        ),
        "selected_heavy_chain": selected_heavy_chain,
        "chains": chains_payload,
        "warnings": deduped_warnings,
        "quality_baseline": quality_baseline,
    }


def is_valid_cdr_region_name(name: str) -> bool:
    return name in CDR_REGION_NAMES
