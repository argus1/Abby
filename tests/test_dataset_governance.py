from __future__ import annotations

import pytest
from pydantic import ValidationError

from abby_api.schemas.common import DatasetSourceProvenance
from abby_api.services.dataset_governance import (
    is_dataset_license_compatible,
    validate_dataset_source_provenance,
    validate_sequence_annotation_dataset_artifact,
)


def _oas_source(**overrides: object) -> DatasetSourceProvenance:
    payload = {
        "dataset_name": "OAS-paired",
        "dataset_role": "training",
        "source_family": "oas",
        "source_label": "Observed Antibody Space paired subset",
        "license": "CC-BY-4.0",
        "license_spdx": "CC-BY-4.0",
        "attribution_required": True,
        "attribution_text": "Observed Antibody Space (OAS), cited per provider terms.",
        "version": "2026-07 snapshot",
        "doi": "10.1234/example-oas",
        "preprocessing_method": "paired-chain filtering + duplicate collapse",
        "notes": ["unit-test fixture"],
    }
    payload.update(overrides)
    return DatasetSourceProvenance(**payload)


def test_license_compatibility_recognizes_supported_tokens() -> None:
    assert is_dataset_license_compatible("CC-BY-4.0") is True
    assert is_dataset_license_compatible("Apache 2.0") is True
    assert is_dataset_license_compatible("proprietary") is False


def test_validate_dataset_source_provenance_accepts_compatible_oas_source() -> None:
    validated = validate_dataset_source_provenance(_oas_source())

    assert validated.license_compatible is True
    assert validated.license_spdx == "CC-BY-4.0"
    assert validated.preprocessing_method == "paired-chain filtering + duplicate collapse"


def test_validate_dataset_source_provenance_rejects_incompatible_license() -> None:
    with pytest.raises(ValueError, match="incompatible or unsupported license"):
        validate_dataset_source_provenance(
            _oas_source(license="proprietary", license_spdx="proprietary")
        )


def test_validate_sequence_annotation_dataset_artifact_accepts_paired_and_vhh_records() -> None:
    artifact = validate_sequence_annotation_dataset_artifact(
        {
            "artifact_name": "cdr_annotation_training_bundle",
            "artifact_role": "training",
            "dataset_sources": [
                _oas_source().model_dump(mode="json"),
                _oas_source(
                    dataset_name="p-IgGen-Zenodo",
                    source_family="paired_unpaired",
                    source_label="p-IgGen Zenodo snapshot",
                    version="v1.0",
                    doi="10.5281/zenodo.1234567",
                    preprocessing_method="paired/unpaired split freeze",
                ).model_dump(mode="json"),
            ],
            "records": [
                {
                    "record_id": "pair-1",
                    "dataset_source_name": "OAS-paired",
                    "split": "train",
                    "antibody_format": "paired_antibody",
                    "heavy_sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEW",
                    "light_sequence": "DIQMTQSPSSLSASVGDRVTITCRASQSIYNLAWYQQKPGKAPKLLIY",
                    "numbering_scheme": "imgt",
                    "cdr_annotations": {"CDR-H3": "ARGYYYYGMDV", "CDR-L3": "QQYNSYP"},
                    "source_pdb_id": "1ABC",
                },
                {
                    "record_id": "vhh-1",
                    "dataset_source_name": "p-IgGen-Zenodo",
                    "split": "qa",
                    "antibody_format": "vhh_single_domain",
                    "heavy_sequence": "QVQLQESGGGLVQAGGSLRLSCAASGRTFSSYAMGWFRQAPGKEREF",
                    "numbering_scheme": "kabat",
                    "cdr_annotations": {"CDR-H3": "ARVGGYDY"},
                    "source_pdb_id": "2DEF",
                },
            ],
        }
    )

    assert artifact.schema_version == "cdr_sequence_annotation_artifact_v1"
    assert len(artifact.dataset_sources) == 2
    assert artifact.records[1].antibody_format == "vhh_single_domain"


def test_validate_sequence_annotation_dataset_artifact_rejects_invalid_record_contract() -> None:
    with pytest.raises(ValidationError):
        validate_sequence_annotation_dataset_artifact(
            {
                "artifact_name": "cdr_annotation_training_bundle",
                "artifact_role": "qa",
                "dataset_sources": [_oas_source().model_dump(mode="json")],
                "records": [
                    {
                        "record_id": "broken-pair",
                        "dataset_source_name": "OAS-paired",
                        "split": "qa",
                        "antibody_format": "paired_antibody",
                        "heavy_sequence": "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMSWVRQAPGKGLEW",
                        "numbering_scheme": "imgt",
                        "cdr_annotations": {"CDR-H3": "ARGYYYYGMDV"},
                    }
                ],
            }
        )