from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import Field, model_validator

from abby_api.schemas.common import AbbyBaseModel, DatasetSourceProvenance

SequenceAnnotationSplit = Literal[
    "train",
    "validation",
    "test",
    "qa",
    "calibration",
    "holdout",
]
AntibodyFormat = Literal[
    "paired_antibody",
    "vhh_single_domain",
    "unknown_antibody_format",
]
NumberingScheme = Literal["imgt", "kabat", "chothia", "aho", "motif_fallback", "unknown"]

_COMPATIBLE_LICENSE_TOKENS = {
    "apache-2.0",
    "bsd-2-clause",
    "bsd-3-clause",
    "cc-by-4.0",
    "cc0-1.0",
    "mit",
    "odc-by-1.0",
}
_COMPATIBLE_LICENSE_ALIASES = {
    "apache 2.0": "apache-2.0",
    "apache license 2.0": "apache-2.0",
    "bsd 2 clause": "bsd-2-clause",
    "bsd 3 clause": "bsd-3-clause",
    "cc by 4.0": "cc-by-4.0",
    "cc-by 4.0": "cc-by-4.0",
    "cc-by-4": "cc-by-4.0",
    "cc-by-4-0": "cc-by-4.0",
    "cc0": "cc0-1.0",
    "cc0-1-0": "cc0-1.0",
    "mit license": "mit",
    "odc by 1.0": "odc-by-1.0",
    "odc-by-1-0": "odc-by-1.0",
}
_OAS_SOURCE_FAMILIES = {"oas", "paired_unpaired", "paired_unpaired_resource"}
_AA_SEQUENCE_RE = re.compile(r"^[A-Z*.-]+$")
_VALID_CDR_KEYS = frozenset({
    "CDR-H1",
    "CDR-H2",
    "CDR-H3",
    "CDR-L1",
    "CDR-L2",
    "CDR-L3",
})


def _normalize_token(value: str | None) -> str:
    if value is None:
        return ""
    normalized = re.sub(r"[^a-z0-9.]+", "-", value.strip().lower()).strip("-")
    return _COMPATIBLE_LICENSE_ALIASES.get(normalized, normalized)


def is_dataset_license_compatible(license_value: str | None) -> bool:
    return _normalize_token(license_value) in _COMPATIBLE_LICENSE_TOKENS


def validate_dataset_source_provenance(
    source: DatasetSourceProvenance,
) -> DatasetSourceProvenance:
    normalized_license = source.license_spdx or source.license
    compatible = is_dataset_license_compatible(normalized_license)
    source_family = str(source.source_family or "").strip().lower()

    if not compatible:
        raise ValueError(
            f"Dataset source {source.dataset_name!r} uses an incompatible or unsupported "
            f"license token: {normalized_license!r}."
        )
    if not source.attribution_required:
        raise ValueError(
            f"Dataset source {source.dataset_name!r} must require attribution for "
            "CompDetRAE governance tracking."
        )
    if not (source.attribution_text and source.attribution_text.strip()):
        raise ValueError(
            f"Dataset source {source.dataset_name!r} is missing attribution text."
        )
    if not (
        (source.version and source.version.strip())
        or (source.doi and source.doi.strip())
    ):
        raise ValueError(
            f"Dataset source {source.dataset_name!r} must record a version or DOI."
        )
    if not (source.preprocessing_method and source.preprocessing_method.strip()):
        raise ValueError(
            f"Dataset source {source.dataset_name!r} must record a preprocessing method."
        )
    if source_family in _OAS_SOURCE_FAMILIES and not compatible:
        raise ValueError(
            f"OAS-like dataset source {source.dataset_name!r} is not licensed for use."
        )

    return source.model_copy(
        update={
            "license_compatible": True,
            "license_spdx": source.license_spdx or _normalize_token(source.license),
        }
    )


class SequenceAnnotationRecord(AbbyBaseModel):
    record_id: str
    dataset_source_name: str
    split: SequenceAnnotationSplit
    antibody_format: AntibodyFormat = "unknown_antibody_format"
    heavy_sequence: str | None = None
    light_sequence: str | None = None
    numbering_scheme: NumberingScheme = "unknown"
    cdr_annotations: dict[str, str] = Field(default_factory=dict)
    source_pdb_id: str | None = None
    source_provenance: str | None = None
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_record(self) -> "SequenceAnnotationRecord":
        def _normalized_sequence(value: str | None) -> str | None:
            if value is None:
                return None
            cleaned = value.strip().upper()
            return cleaned or None

        heavy_sequence = _normalized_sequence(self.heavy_sequence)
        light_sequence = _normalized_sequence(self.light_sequence)
        if heavy_sequence is None and light_sequence is None:
            raise ValueError("Sequence annotation record must include a heavy or light sequence.")

        sequence_fields = (
            ("heavy_sequence", heavy_sequence),
            ("light_sequence", light_sequence),
        )
        for label, sequence in sequence_fields:
            if sequence is not None and not _AA_SEQUENCE_RE.fullmatch(sequence):
                raise ValueError(
                    f"Sequence annotation record field {label} contains invalid residue tokens."
                )

        if self.antibody_format == "paired_antibody" and (
            heavy_sequence is None or light_sequence is None
        ):
            raise ValueError(
                "Paired-antibody annotation records must include both heavy and light sequences."
            )

        invalid_cdr_keys = sorted(set(self.cdr_annotations) - _VALID_CDR_KEYS)
        if invalid_cdr_keys:
            raise ValueError(
                "Sequence annotation record contains unsupported CDR keys: "
                f"{', '.join(invalid_cdr_keys)}"
            )

        return self.model_copy(
            update={
                "heavy_sequence": heavy_sequence,
                "light_sequence": light_sequence,
                "cdr_annotations": {
                    key: value.strip().upper()
                    for key, value in self.cdr_annotations.items()
                    if value is not None and str(value).strip()
                },
            }
        )


class SequenceAnnotationDatasetArtifact(AbbyBaseModel):
    artifact_name: str
    artifact_role: Literal["training", "qa", "evaluation"] = "qa"
    schema_version: str = "cdr_sequence_annotation_artifact_v1"
    dataset_sources: list[DatasetSourceProvenance] = Field(default_factory=list)
    records: list[SequenceAnnotationRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_artifact(self) -> "SequenceAnnotationDatasetArtifact":
        if not self.records:
            raise ValueError(
                "Sequence annotation dataset artifact must include at least one record."
            )
        if not self.dataset_sources:
            raise ValueError(
                "Sequence annotation dataset artifact must include at least one dataset source."
            )

        validated_sources: list[DatasetSourceProvenance] = []
        source_lookup: dict[str, DatasetSourceProvenance] = {}
        for source in self.dataset_sources:
            validated = validate_dataset_source_provenance(source)
            if validated.dataset_name in source_lookup:
                raise ValueError(
                    f"Duplicate dataset source name in artifact: {validated.dataset_name!r}."
                )
            validated_sources.append(validated)
            source_lookup[validated.dataset_name] = validated

        for record in self.records:
            if record.dataset_source_name not in source_lookup:
                raise ValueError(
                    "Sequence annotation record references an unknown dataset source: "
                    f"{record.dataset_source_name!r}."
                )

        return self.model_copy(update={"dataset_sources": validated_sources})


def validate_sequence_annotation_dataset_artifact(
    payload: dict[str, Any] | SequenceAnnotationDatasetArtifact,
) -> SequenceAnnotationDatasetArtifact:
    if isinstance(payload, SequenceAnnotationDatasetArtifact):
        return SequenceAnnotationDatasetArtifact.model_validate(payload.model_dump(mode="json"))
    return SequenceAnnotationDatasetArtifact.model_validate(payload)