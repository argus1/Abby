from __future__ import annotations

from abby_api.services.baseline_models import derive_delta_g_kcal_mol, run_baseline_affinity_models


def test_baseline_scoring_changes_with_feature_values() -> None:
    descriptors_low = {
        "total_residues": 40.0,
        "interface_contact_proxy": 1.0,
        "interface_density_proxy": 0.025,
        "global_apolar_fraction": 0.20,
        "global_charged_fraction": 0.20,
        "global_polar_fraction": 0.30,
        "global_aromatic_fraction": 0.10,
        "partner_size_ratio": 0.50,
        "paired_apolar_proxy": 1.0,
        "multi_model_flag": 0.0,
        "antibody_mode_flag": 0.0,
    }
    descriptors_high = {
        **descriptors_low,
        "interface_contact_proxy": 6.0,
        "interface_density_proxy": 0.15,
        "global_apolar_fraction": 0.45,
        "partner_size_ratio": 0.95,
        "paired_apolar_proxy": 3.0,
    }

    score_low = run_baseline_affinity_models(descriptors_low)
    score_high = run_baseline_affinity_models(descriptors_high)

    assert score_low.consensus_log_k != score_high.consensus_log_k
    assert score_low.scores[0].log_k != score_high.scores[0].log_k


def test_delta_g_derivation_respects_temperature() -> None:
    log_k = -7.0
    delta_g_cool = derive_delta_g_kcal_mol(log_k, temperature_kelvin=280.0)
    delta_g_warm = derive_delta_g_kcal_mol(log_k, temperature_kelvin=320.0)
    assert delta_g_warm < delta_g_cool
