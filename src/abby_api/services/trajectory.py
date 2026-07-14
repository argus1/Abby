from __future__ import annotations

"""Trajectory-aware aggregation service using MDAnalysis (optional).

Phase 5B of the Abby roadmap: Trajectory-aware aggregation.

This module provides:
- Optional MDAnalysis integration for traversing MD trajectory files.
- Averaged / ensemble structural summaries computed from trajectory frames.
- Helper to enrich the descriptor bundle with simulation-derived summary data.

MDAnalysis is an optional dependency.  All public functions degrade
gracefully when it is not installed, returning stub observations with
an explicit ``MDANALYSIS_NOT_AVAILABLE`` note so callers can detect the
fallback without branching on import errors.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------


def is_mdanalysis_available() -> bool:
    """Return True if MDAnalysis is importable."""
    try:
        import MDAnalysis  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrajectoryFrameSummary:
    """Averaged structural metrics extracted from a single trajectory frame."""

    frame_index: int
    radius_of_gyration_angstrom: float
    atom_count: int
    center_of_mass: tuple[float, float, float]


@dataclass(frozen=True)
class TrajectorySummary:
    """Ensemble structural summary aggregated across all trajectory frames.

    When MDAnalysis is not available or the trajectory could not be read, all
    numeric fields default to ``0.0`` and ``notes`` contains the reason.
    """

    mdanalysis_available: bool
    frame_count: int
    mean_radius_of_gyration_angstrom: float
    std_radius_of_gyration_angstrom: float
    min_radius_of_gyration_angstrom: float
    max_radius_of_gyration_angstrom: float
    mean_atom_count: float
    notes: list[str] = field(default_factory=list)

    # Per-frame summaries (may be empty for large trajectories or stub results).
    frame_summaries: list[TrajectoryFrameSummary] = field(default_factory=list)


_STUB_SUMMARY = TrajectorySummary(
    mdanalysis_available=False,
    frame_count=0,
    mean_radius_of_gyration_angstrom=0.0,
    std_radius_of_gyration_angstrom=0.0,
    min_radius_of_gyration_angstrom=0.0,
    max_radius_of_gyration_angstrom=0.0,
    mean_atom_count=0.0,
    notes=["MDANALYSIS_NOT_AVAILABLE"],
    frame_summaries=[],
)


# ---------------------------------------------------------------------------
# Core trajectory functions
# ---------------------------------------------------------------------------


def compute_trajectory_summary(
    trajectory_path: Path,
    topology_path: Path | None = None,
    *,
    max_frames: int = 1000,
) -> TrajectorySummary:
    """Traverse a trajectory file and return an ensemble structural summary.

    Parameters
    ----------
    trajectory_path:
        Path to the trajectory file (e.g. ``.trr``, ``.xtc``, ``.dcd``).
    topology_path:
        Optional topology file (e.g. ``.gro``, ``.pdb``) required by some
        trajectory formats.  When *None* and the format needs it, MDAnalysis
        will raise and the function returns a stub summary.
    max_frames:
        Maximum number of evenly-sampled frames to process.  Processing is
        skipped for frames beyond this limit to bound memory use.

    Returns
    -------
    TrajectorySummary
        Ensemble summary.  ``mdanalysis_available`` is ``False`` and
        ``frame_count`` is ``0`` when MDAnalysis is not installed or the
        trajectory could not be read.
    """
    if not is_mdanalysis_available():
        return _STUB_SUMMARY

    try:
        return _compute_summary_with_mdanalysis(
            trajectory_path=trajectory_path,
            topology_path=topology_path,
            max_frames=max_frames,
        )
    except Exception as exc:
        return TrajectorySummary(
            mdanalysis_available=True,
            frame_count=0,
            mean_radius_of_gyration_angstrom=0.0,
            std_radius_of_gyration_angstrom=0.0,
            min_radius_of_gyration_angstrom=0.0,
            max_radius_of_gyration_angstrom=0.0,
            mean_atom_count=0.0,
            notes=[f"TRAJECTORY_READ_FAILED:{exc}"],
            frame_summaries=[],
        )


def _compute_summary_with_mdanalysis(
    *,
    trajectory_path: Path,
    topology_path: Path | None,
    max_frames: int,
) -> TrajectorySummary:
    """Internal: use MDAnalysis to iterate frames and collect metrics."""
    import MDAnalysis as mda  # type: ignore[import]
    from math import sqrt

    topo_arg = str(topology_path) if topology_path is not None else str(trajectory_path)
    universe = mda.Universe(topo_arg, str(trajectory_path))
    all_atoms = universe.select_atoms("all")

    n_frames = len(universe.trajectory)
    stride = max(1, n_frames // max_frames)

    rg_values: list[float] = []
    atom_counts: list[int] = []
    frame_summaries: list[TrajectoryFrameSummary] = []

    for ts in universe.trajectory[::stride]:
        positions = all_atoms.positions
        n_atoms = len(positions)
        if n_atoms == 0:
            continue
        # Center of mass (uniform mass approximation).
        com = (
            float(positions[:, 0].mean()),
            float(positions[:, 1].mean()),
            float(positions[:, 2].mean()),
        )
        # Radius of gyration (Å, uniform mass).
        rg = float(
            sqrt(
                (
                    ((positions[:, 0] - com[0]) ** 2)
                    + ((positions[:, 1] - com[1]) ** 2)
                    + ((positions[:, 2] - com[2]) ** 2)
                ).mean()
            )
        )
        rg_values.append(rg)
        atom_counts.append(n_atoms)
        frame_summaries.append(
            TrajectoryFrameSummary(
                frame_index=int(ts.frame),
                radius_of_gyration_angstrom=round(rg, 4),
                atom_count=n_atoms,
                center_of_mass=(round(com[0], 4), round(com[1], 4), round(com[2], 4)),
            )
        )

    if not rg_values:
        return TrajectorySummary(
            mdanalysis_available=True,
            frame_count=n_frames,
            mean_radius_of_gyration_angstrom=0.0,
            std_radius_of_gyration_angstrom=0.0,
            min_radius_of_gyration_angstrom=0.0,
            max_radius_of_gyration_angstrom=0.0,
            mean_atom_count=0.0,
            notes=["NO_ATOMS_IN_TRAJECTORY"],
            frame_summaries=[],
        )

    mean_rg = sum(rg_values) / len(rg_values)
    variance = sum((r - mean_rg) ** 2 for r in rg_values) / len(rg_values)
    std_rg = sqrt(variance)

    return TrajectorySummary(
        mdanalysis_available=True,
        frame_count=n_frames,
        mean_radius_of_gyration_angstrom=round(mean_rg, 4),
        std_radius_of_gyration_angstrom=round(std_rg, 4),
        min_radius_of_gyration_angstrom=round(min(rg_values), 4),
        max_radius_of_gyration_angstrom=round(max(rg_values), 4),
        mean_atom_count=round(sum(atom_counts) / len(atom_counts), 2),
        notes=["TRAJECTORY_SUMMARY_FROM_MDANALYSIS"],
        frame_summaries=frame_summaries,
    )


# ---------------------------------------------------------------------------
# Descriptor enrichment
# ---------------------------------------------------------------------------


def enrich_descriptors_from_trajectory(
    descriptors: dict[str, float],
    trajectory_summary: TrajectorySummary,
) -> tuple[dict[str, float], list[str]]:
    """Return an enriched descriptor dict and supplementary notes.

    Adds trajectory-derived fields alongside existing descriptors without
    mutating the original dict.  When MDAnalysis was not available or the
    trajectory produced no frames the function returns the original descriptor
    dict unchanged and appends an explanatory note.

    Parameters
    ----------
    descriptors:
        Existing descriptor dict from ``build_descriptor_bundle``.
    trajectory_summary:
        ``TrajectorySummary`` from ``compute_trajectory_summary``.

    Returns
    -------
    tuple[dict[str, float], list[str]]
        ``(enriched_descriptors, additional_notes)``
    """
    notes: list[str] = []

    if not trajectory_summary.mdanalysis_available or trajectory_summary.frame_count == 0:
        notes.append("TRAJECTORY_DESCRIPTORS_NOT_ENRICHED")
        return dict(descriptors), notes

    enriched = dict(descriptors)
    enriched["trajectory_mean_radius_of_gyration_angstrom"] = (
        trajectory_summary.mean_radius_of_gyration_angstrom
    )
    enriched["trajectory_std_radius_of_gyration_angstrom"] = (
        trajectory_summary.std_radius_of_gyration_angstrom
    )
    enriched["trajectory_min_radius_of_gyration_angstrom"] = (
        trajectory_summary.min_radius_of_gyration_angstrom
    )
    enriched["trajectory_max_radius_of_gyration_angstrom"] = (
        trajectory_summary.max_radius_of_gyration_angstrom
    )
    enriched["trajectory_frame_count"] = float(trajectory_summary.frame_count)
    enriched["trajectory_mean_atom_count"] = trajectory_summary.mean_atom_count

    notes.append("TRAJECTORY_DESCRIPTORS_ENRICHED_FROM_MDANALYSIS")
    return enriched, notes
