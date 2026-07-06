from __future__ import annotations

from dataclasses import dataclass

from abby_api.schemas.common import ConfidenceClass

R_KCAL_PER_MOL_K = 0.00198720425864083


@dataclass(frozen=True)
class BaselineScore:
    model_id: str
    log_k: float
    r_validation: float


@dataclass(frozen=True)
class BaselineScoringResult:
    scores: list[BaselineScore]
    consensus_log_k: float
    confidence: ConfidenceClass
    ood_flag: bool
    interval_half_width: float


def _feature(descriptors: dict[str, float], name: str, default: float = 0.0) -> float:
    return float(descriptors.get(name, default))


def score_ic_nis_baseline(descriptors: dict[str, float]) -> BaselineScore:
    log_k = (
        -5.85
        - (0.18 * _feature(descriptors, "interface_contact_proxy"))
        - (0.90 * _feature(descriptors, "global_apolar_fraction"))
        + (0.35 * _feature(descriptors, "global_charged_fraction"))
        - (0.25 * _feature(descriptors, "partner_size_ratio"))
        - (0.20 * _feature(descriptors, "antibody_mode_flag"))
    )
    return BaselineScore(model_id="linear_ic_nis_v1", log_k=round(log_k, 2), r_validation=0.79)


def score_surface_balance_baseline(descriptors: dict[str, float]) -> BaselineScore:
    log_k = (
        -5.10
        - (0.55 * _feature(descriptors, "interface_density_proxy"))
        - (0.70 * _feature(descriptors, "global_aromatic_fraction"))
        - (0.45 * _feature(descriptors, "global_apolar_fraction"))
        + (0.25 * _feature(descriptors, "global_polar_fraction"))
        - (0.10 * _feature(descriptors, "multi_model_flag"))
    )
    return BaselineScore(model_id="surface_balance_v1", log_k=round(log_k, 2), r_validation=0.73)


def score_mixed_baseline(descriptors: dict[str, float], linear: BaselineScore, surface: BaselineScore) -> BaselineScore:
    correction = -0.08 * _feature(descriptors, "paired_apolar_proxy")
    log_k = (0.65 * linear.log_k) + (0.35 * surface.log_k) + correction
    return BaselineScore(model_id="mixed_baseline_v1", log_k=round(log_k, 2), r_validation=0.85)


def run_baseline_affinity_models(descriptors: dict[str, float]) -> BaselineScoringResult:
    linear = score_ic_nis_baseline(descriptors)
    surface = score_surface_balance_baseline(descriptors)
    mixed = score_mixed_baseline(descriptors, linear, surface)
    scores = [mixed, linear, surface]

    weighted_sum = (0.5 * mixed.log_k) + (0.3 * linear.log_k) + (0.2 * surface.log_k)
    consensus_log_k = round(weighted_sum, 2)
    spread = max(score.log_k for score in scores) - min(score.log_k for score in scores)
    interval_half_width = round(max(0.25, min(0.9, 0.2 + (spread / 2.5))), 2)

    total_residues = _feature(descriptors, "total_residues", default=0.0)
    interface_density = _feature(descriptors, "interface_density_proxy")
    confidence: ConfidenceClass = "high" if total_residues >= 2 and interface_density >= 0.01 else "medium"
    ood_flag = total_residues < 1

    return BaselineScoringResult(
        scores=scores,
        consensus_log_k=consensus_log_k,
        confidence=confidence,
        ood_flag=ood_flag,
        interval_half_width=interval_half_width,
    )


def derive_delta_g_kcal_mol(log_k: float, temperature_kelvin: float = 298.15) -> float:
    temp = max(250.0, min(350.0, float(temperature_kelvin)))
    factor = 2.303 * R_KCAL_PER_MOL_K * temp
    return round(log_k * factor, 2)


def derive_k_from_log_k(log_k: float) -> float:
    return round(10 ** log_k, 10)


def derive_thermodynamic_outputs(log_k: float, temperature_kelvin: float = 298.15) -> dict[str, float]:
    return {
        "log_k": round(log_k, 2),
        "delta_g_kcal_mol": derive_delta_g_kcal_mol(log_k, temperature_kelvin),
        "k": derive_k_from_log_k(log_k),
    }
