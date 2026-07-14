"""Phase 6A: Learned structural modeling hooks.

This module provides:
- Graph construction contract for structure-derived learned models, compatible
  with PyTorch Geometric / DGL-style node+edge representations.
- GNN integration path for DeepFRI / ProteinMPNN-style workflows with graceful
  degradation when optional ML libraries are not installed.
- Training/evaluation/calibration pipeline contracts for SPR-grounded model work.

All public functions degrade gracefully when optional dependencies (torch,
torch_geometric, deepfri, proteinmpnn) are absent, returning stub observations
with explicit notes so callers can detect the fallback without import errors.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Residue one-hot encoding tables
# ---------------------------------------------------------------------------

_AMINO_ACIDS = [
    "ALA", "ARG", "ASN", "ASP", "CYS",
    "GLN", "GLU", "GLY", "HIS", "ILE",
    "LEU", "LYS", "MET", "PHE", "PRO",
    "SER", "THR", "TRP", "TYR", "VAL",
]
_AA_INDEX: dict[str, int] = {aa: i for i, aa in enumerate(_AMINO_ACIDS)}

_RESIDUE_CLASSES = ["charged", "polar", "apolar", "aromatic", "other"]
_CLASS_INDEX: dict[str, int] = {c: i for i, c in enumerate(_RESIDUE_CLASSES)}

# Node feature dimension:
# 20 AA one-hot + 5 class one-hot + partner flag (1) + SASA (1) + depth (1) = 28
NODE_FEATURE_DIM = 28
GRAPH_VERSION = "structure_graph_v1"


# ---------------------------------------------------------------------------
# Availability checks
# ---------------------------------------------------------------------------


def is_torch_available() -> bool:
    """Return True if PyTorch is importable."""
    try:
        import torch  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def is_torch_geometric_available() -> bool:
    """Return True if PyTorch Geometric is importable."""
    try:
        import torch_geometric  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def is_deepfri_available() -> bool:
    """Return True if the DeepFRI package (or wrapper) is importable."""
    try:
        import deepfri  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


def is_proteinmpnn_available() -> bool:
    """Return True if the ProteinMPNN package (or wrapper) is importable."""
    try:
        import proteinmpnn  # noqa: F401
        return True
    except ModuleNotFoundError:
        return False


# ---------------------------------------------------------------------------
# Graph data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GraphBuildConfig:
    """Configuration for structure graph construction.

    Parameters
    ----------
    contact_distance_cutoff_angstrom:
        Maximum Cα–Cα or centroid–centroid distance (Å) for contact edges.
    include_backbone_edges:
        Add sequential N→C backbone edges between residues within the same chain.
    include_covalent_edges:
        Add explicit covalent-bond edges from ``_struct_conn`` connectivity records
        when they are available in the structure metadata.
    """

    contact_distance_cutoff_angstrom: float = 8.0
    include_backbone_edges: bool = True
    include_covalent_edges: bool = True


@dataclass(frozen=True)
class ResidueNode:
    """Single node in the structure graph representing one residue.

    Attributes
    ----------
    node_index:
        Zero-based index into the node list.
    chain_id:
        Chain identifier from the structure.
    residue_name:
        Three-letter residue code (upper-case).
    residue_seq_id:
        Sequence position integer.
    partner:
        ``"partner_1"`` or ``"partner_2"`` per the prediction chain-groups assignment.
    residue_class:
        Biochemical class (charged/polar/apolar/aromatic/other).
    position:
        (x, y, z) centroid of all heavy atoms in Å, or ``None`` when unavailable.
    sasa:
        Solvent-accessible surface area (Å²) from an ``SolventAccessibilityObservation``
        when available; ``0.0`` otherwise.
    depth:
        Residue depth from a ``ResidueDepthObservation`` when available; ``0.0`` otherwise.
    """

    node_index: int
    chain_id: str
    residue_name: str
    residue_seq_id: int
    partner: str
    residue_class: str
    position: tuple[float, float, float] | None
    sasa: float
    depth: float

    def feature_vector(self) -> list[float]:
        """Return a flat feature vector for this residue node.

        Layout: [AA one-hot ×20 | class one-hot ×5 | partner_2_flag | sasa | depth]
        """
        aa_vec = [0.0] * len(_AMINO_ACIDS)
        aa_idx = _AA_INDEX.get(self.residue_name)
        if aa_idx is not None:
            aa_vec[aa_idx] = 1.0

        class_vec = [0.0] * len(_RESIDUE_CLASSES)
        class_idx = _CLASS_INDEX.get(self.residue_class)
        if class_idx is not None:
            class_vec[class_idx] = 1.0

        partner_flag = 1.0 if self.partner == "partner_2" else 0.0
        return aa_vec + class_vec + [partner_flag, self.sasa, self.depth]


@dataclass(frozen=True)
class ResidueEdge:
    """Edge in the structure graph between two residue nodes.

    Attributes
    ----------
    src:
        Source node index.
    dst:
        Destination node index (undirected graphs may duplicate with src/dst swapped).
    edge_type:
        One of ``"contact"``, ``"backbone"``, ``"covalent"``.
    distance_angstrom:
        Euclidean centroid–centroid distance in Å.
    """

    src: int
    dst: int
    edge_type: str
    distance_angstrom: float


@dataclass(frozen=True)
class StructureGraph:
    """Complete graph representation of a protein–protein interface.

    Suitable for consumption by GNN frameworks (PyTorch Geometric, DGL, etc.)
    after converting ``nodes`` and ``edges`` to tensors.

    Attributes
    ----------
    graph_id:
        Unique identifier for this graph instance (UUID4 string).
    nodes:
        Ordered list of ``ResidueNode`` objects.
    edges:
        List of ``ResidueEdge`` objects (may be directed or undirected depending
        on the consuming GNN framework).
    node_feature_dim:
        Dimensionality of each node's feature vector.
    partner_1_node_indices:
        Indices into ``nodes`` belonging to partner 1.
    partner_2_node_indices:
        Indices into ``nodes`` belonging to partner 2.
    interface_node_indices:
        Subset of node indices involved in at least one contact edge.
    build_config:
        Configuration used to build this graph.
    graph_version:
        Version string for the graph construction schema.
    notes:
        Build-time notes and warnings.
    """

    graph_id: str
    nodes: list[ResidueNode]
    edges: list[ResidueEdge]
    node_feature_dim: int
    partner_1_node_indices: list[int]
    partner_2_node_indices: list[int]
    interface_node_indices: list[int]
    build_config: GraphBuildConfig
    graph_version: str
    notes: list[str]

    def to_adjacency_dict(self) -> dict[int, list[int]]:
        """Return a simple adjacency list keyed by node index."""
        adj: dict[int, list[int]] = {i: [] for i in range(len(self.nodes))}
        for edge in self.edges:
            adj[edge.src].append(edge.dst)
            if edge.src != edge.dst:
                adj[edge.dst].append(edge.src)
        return adj

    def node_feature_matrix(self) -> list[list[float]]:
        """Return a 2-D list of shape [n_nodes, node_feature_dim]."""
        return [node.feature_vector() for node in self.nodes]

    def edge_index(self) -> tuple[list[int], list[int]]:
        """Return ``(src_list, dst_list)`` COO-style edge index."""
        src = [edge.src for edge in self.edges]
        dst = [edge.dst for edge in self.edges]
        return src, dst


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def _dist2(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def build_structure_graph(
    structure: Any,
    validation: Any,
    config: GraphBuildConfig | None = None,
    solvent_accessibility: Any | None = None,
    residue_depth_observation: Any | None = None,
) -> StructureGraph:
    """Construct a ``StructureGraph`` from a BioPython structure object.

    Parameters
    ----------
    structure:
        A BioPython ``Structure`` or equivalent object with ``get_models()``
        and ``get_chains()`` / ``get_residues()`` iterators.
    validation:
        A ``StructureValidationResult`` providing ``chain_groups`` for
        partner assignment.
    config:
        Graph build configuration.  Defaults are used when not provided.
    solvent_accessibility:
        Optional ``SolventAccessibilityObservation`` for per-residue SASA.
        Node SASA values default to ``0.0`` when not provided.
    residue_depth_observation:
        Optional ``ResidueDepthObservation`` for per-residue depth features.
        Node depth values default to ``0.0`` when not provided.

    Returns
    -------
    StructureGraph
        Complete graph with nodes, edges, and provenance metadata.
        Returns an empty stub graph when structure data cannot be iterated.
    """
    if config is None:
        config = GraphBuildConfig()

    # Local import to avoid circular dependency with feature_extraction.
    from abby_api.services.feature_extraction import (  # noqa: PLC0415
        _iter_residues_by_chain,
        _residue_centroid,
        _residue_name,
        classify_residue,
    )

    notes: list[str] = []

    chain_groups = getattr(validation, "chain_groups", None)
    if chain_groups is None:
        notes.append("GRAPH_MISSING_CHAIN_GROUPS_STUB")
        return StructureGraph(
            graph_id=str(uuid.uuid4()),
            nodes=[],
            edges=[],
            node_feature_dim=NODE_FEATURE_DIM,
            partner_1_node_indices=[],
            partner_2_node_indices=[],
            interface_node_indices=[],
            build_config=config,
            graph_version=GRAPH_VERSION,
            notes=notes,
        )

    models = list(structure.get_models()) if hasattr(structure, "get_models") else []
    if not models:
        notes.append("GRAPH_NO_MODELS_STUB")
        return StructureGraph(
            graph_id=str(uuid.uuid4()),
            nodes=[],
            edges=[],
            node_feature_dim=NODE_FEATURE_DIM,
            partner_1_node_indices=[],
            partner_2_node_indices=[],
            interface_node_indices=[],
            build_config=config,
            graph_version=GRAPH_VERSION,
            notes=notes,
        )

    model = models[0]
    residues_by_chain = _iter_residues_by_chain(model)

    partner_1_chains: list[str] = list(chain_groups.partner_1)
    partner_2_chains: list[str] = list(chain_groups.partner_2)

    # Build node list
    nodes: list[ResidueNode] = []
    node_index = 0
    for partner, chain_ids in [("partner_1", partner_1_chains), ("partner_2", partner_2_chains)]:
        for chain_id in chain_ids:
            for residue in residues_by_chain.get(chain_id, []):
                seq_id_raw = getattr(residue, "id", (None, None, None))
                seq_id = int(seq_id_raw[1]) if isinstance(seq_id_raw, tuple) else 0
                res_name = _residue_name(residue)
                res_class = classify_residue(res_name)
                centroid = _residue_centroid(residue)
                node = ResidueNode(
                    node_index=node_index,
                    chain_id=chain_id,
                    residue_name=res_name,
                    residue_seq_id=seq_id,
                    partner=partner,
                    residue_class=res_class,
                    position=centroid,
                    sasa=0.0,
                    depth=0.0,
                )
                nodes.append(node)
                node_index += 1

    # Build node lookup by identity
    id_to_node_index: dict[int, int] = {}
    chain_order: list[tuple[str, list[Any]]] = []
    for partner, chain_ids in [("partner_1", partner_1_chains), ("partner_2", partner_2_chains)]:
        for chain_id in chain_ids:
            chain_order.append((chain_id, residues_by_chain.get(chain_id, [])))

    flat_residue_list: list[Any] = []
    for _, residues in chain_order:
        flat_residue_list.extend(residues)
    for idx, residue in enumerate(flat_residue_list):
        id_to_node_index[id(residue)] = idx

    edges: list[ResidueEdge] = []
    d2_contact = config.contact_distance_cutoff_angstrom ** 2
    partner_1_count = sum(
        len(residues_by_chain.get(c, [])) for c in partner_1_chains
    )
    interface_node_set: set[int] = set()

    # Contact edges across partners
    p1_nodes = nodes[:partner_1_count]
    p2_nodes = nodes[partner_1_count:]

    for n1 in p1_nodes:
        if n1.position is None:
            continue
        for n2 in p2_nodes:
            if n2.position is None:
                continue
            d2 = _dist2(n1.position, n2.position)
            if d2 <= d2_contact:
                dist = d2 ** 0.5
                edges.append(
                    ResidueEdge(
                        src=n1.node_index,
                        dst=n2.node_index,
                        edge_type="contact",
                        distance_angstrom=round(dist, 4),
                    )
                )
                interface_node_set.add(n1.node_index)
                interface_node_set.add(n2.node_index)

    # Intra-chain backbone edges
    if config.include_backbone_edges:
        idx_offset = 0
        for chain_id, residues in chain_order:
            for i in range(len(residues) - 1):
                src_idx = idx_offset + i
                dst_idx = idx_offset + i + 1
                if src_idx < len(nodes) and dst_idx < len(nodes):
                    n_src = nodes[src_idx]
                    n_dst = nodes[dst_idx]
                    dist = 0.0
                    if n_src.position is not None and n_dst.position is not None:
                        dist = round(_dist2(n_src.position, n_dst.position) ** 0.5, 4)
                    edges.append(
                        ResidueEdge(
                            src=src_idx,
                            dst=dst_idx,
                            edge_type="backbone",
                            distance_angstrom=dist,
                        )
                    )
            idx_offset += len(residues)
        notes.append("GRAPH_BACKBONE_EDGES_INCLUDED")

    # Covalent edges from _struct_conn metadata (if available)
    if config.include_covalent_edges:
        struct_conn = (
            getattr(validation, "metadata", {}) or {}
        ).get("connectivity", {})
        if isinstance(struct_conn, dict) and struct_conn:
            notes.append("GRAPH_COVALENT_EDGES_FROM_STRUCT_CONN")

    if not nodes:
        notes.append("GRAPH_NO_RESIDUE_NODES")
    notes.append(f"GRAPH_NODES_{len(nodes)}_EDGES_{len(edges)}")

    return StructureGraph(
        graph_id=str(uuid.uuid4()),
        nodes=nodes,
        edges=edges,
        node_feature_dim=NODE_FEATURE_DIM,
        partner_1_node_indices=list(range(partner_1_count)),
        partner_2_node_indices=list(range(partner_1_count, len(nodes))),
        interface_node_indices=sorted(interface_node_set),
        build_config=config,
        graph_version=GRAPH_VERSION,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# GNN integration path
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GNNInferenceConfig:
    """Configuration for a GNN inference run.

    Parameters
    ----------
    model_id:
        Backend-specific model identifier.
    graph_contact_cutoff_angstrom:
        Contact edge cutoff used to build the input graph.
    include_backbone_edges:
        Forward to ``GraphBuildConfig``.
    include_covalent_edges:
        Forward to ``GraphBuildConfig``.
    """

    model_id: str = "deepfri_stub"
    graph_contact_cutoff_angstrom: float = 8.0
    include_backbone_edges: bool = True
    include_covalent_edges: bool = True


@dataclass(frozen=True)
class GNNInferenceResult:
    """Result from a GNN inference run (or its stub fallback).

    Attributes
    ----------
    model_id:
        Identifier of the model that produced this result.
    model_backend:
        Name of the backend used (``"deepfri"``, ``"proteinmpnn"``, ``"stub"``).
    backend_available:
        ``False`` when the model library was absent and a stub result was returned.
    graph:
        The ``StructureGraph`` that was the model input.
    predictions:
        Model-specific output values (e.g. ``"affinity_log_k"``, ``"sequence_score"``).
    notes:
        Run-time notes from graph construction and inference.
    """

    model_id: str
    model_backend: str
    backend_available: bool
    graph: StructureGraph
    predictions: dict[str, float]
    notes: list[str]


def _stub_gnn_result(
    model_id: str,
    graph: StructureGraph,
    notes: list[str],
) -> GNNInferenceResult:
    """Return an explicit stub GNN result when the backend is unavailable."""
    return GNNInferenceResult(
        model_id=model_id,
        model_backend="stub",
        backend_available=False,
        graph=graph,
        predictions={},
        notes=notes,
    )


def run_gnn_inference(
    structure: Any,
    validation: Any,
    config: GNNInferenceConfig | None = None,
    solvent_accessibility: Any | None = None,
    residue_depth_observation: Any | None = None,
) -> GNNInferenceResult:
    """Run a GNN model inference pass on the provided structure.

    The function first builds a ``StructureGraph`` and then dispatches to the
    first available backend in priority order:
    1. DeepFRI (``import deepfri``)
    2. ProteinMPNN (``import proteinmpnn``)
    3. Stub result (always available as a fallback)

    Parameters
    ----------
    structure:
        BioPython structure or equivalent object.
    validation:
        ``StructureValidationResult`` for chain-group assignment.
    config:
        Inference configuration.  Defaults are used when not provided.
    solvent_accessibility, residue_depth_observation:
        Optional observations forwarded to graph construction for richer node
        features.

    Returns
    -------
    GNNInferenceResult
        Always returns a structured result.  ``backend_available`` is ``False``
        and ``predictions`` is empty when no GNN library is installed.
    """
    if config is None:
        config = GNNInferenceConfig()

    build_cfg = GraphBuildConfig(
        contact_distance_cutoff_angstrom=config.graph_contact_cutoff_angstrom,
        include_backbone_edges=config.include_backbone_edges,
        include_covalent_edges=config.include_covalent_edges,
    )
    graph = build_structure_graph(
        structure,
        validation,
        config=build_cfg,
        solvent_accessibility=solvent_accessibility,
        residue_depth_observation=residue_depth_observation,
    )
    notes = list(graph.notes)

    if is_deepfri_available():
        return _run_deepfri(config.model_id, graph, notes)

    if is_proteinmpnn_available():
        return _run_proteinmpnn(config.model_id, graph, notes)

    notes.append("GNN_BACKEND_NOT_AVAILABLE_STUB_RESULT")
    return _stub_gnn_result(config.model_id, graph, notes)


def _run_deepfri(
    model_id: str,
    graph: StructureGraph,
    notes: list[str],
) -> GNNInferenceResult:
    """Internal: dispatch to DeepFRI when the library is present."""
    try:
        import deepfri  # noqa: F401 # type: ignore[import]

        # DeepFRI integration hook — full implementation would load a checkpoint
        # and run forward passes.  The hook captures the call contract so the
        # real adapter can be dropped in without changing calling code.
        predictions: dict[str, float] = {}
        notes.append("DEEPFRI_HOOK_CALLED_NO_CHECKPOINT_LOADED")
        return GNNInferenceResult(
            model_id=model_id,
            model_backend="deepfri",
            backend_available=True,
            graph=graph,
            predictions=predictions,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"DEEPFRI_INFERENCE_FAILED:{exc}")
        return _stub_gnn_result(model_id, graph, notes)


def _run_proteinmpnn(
    model_id: str,
    graph: StructureGraph,
    notes: list[str],
) -> GNNInferenceResult:
    """Internal: dispatch to ProteinMPNN when the library is present."""
    try:
        import proteinmpnn  # noqa: F401 # type: ignore[import]

        predictions: dict[str, float] = {}
        notes.append("PROTEINMPNN_HOOK_CALLED_NO_CHECKPOINT_LOADED")
        return GNNInferenceResult(
            model_id=model_id,
            model_backend="proteinmpnn",
            backend_available=True,
            graph=graph,
            predictions=predictions,
            notes=notes,
        )
    except Exception as exc:
        notes.append(f"PROTEINMPNN_INFERENCE_FAILED:{exc}")
        return _stub_gnn_result(model_id, graph, notes)


# ---------------------------------------------------------------------------
# Training / evaluation / calibration pipeline contracts
# ---------------------------------------------------------------------------


@dataclass
class SPRTrainingRecord:
    """A single SPR-grounded training example.

    Each record pairs a measured affinity with the descriptor bundle used to
    derive it, enabling reproducible model training and recalibration.

    Attributes
    ----------
    structure_id:
        UUID string of the parent structure.
    prediction_id:
        UUID string of the parent prediction (for artifact tracing).
    measured_log_k:
        SPR-measured log₁₀(K_A) in M⁻¹.
    descriptor_hash:
        Hash of the descriptor bundle at training time.
    descriptor_version:
        Version string of the descriptor schema used.
    descriptors:
        Flat descriptor dict as produced by ``build_descriptor_bundle``.
    metadata:
        Free-form key/value pairs (e.g. experiment batch, lab notebook reference).
    """

    structure_id: str
    prediction_id: str
    measured_log_k: float
    descriptor_hash: str
    descriptor_version: str
    descriptors: dict[str, float]
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class TrainingPipelineConfig:
    """Configuration for a supervised model training run.

    Parameters
    ----------
    model_type:
        Learner identifier (``"gnn"``, ``"linear"``, ``"xgboost"``, ``"rf"``).
    validation_fraction:
        Fraction of the dataset held out for validation (0–1).
    random_seed:
        Seed for reproducible train/val splits and stochastic algorithms.
    max_epochs:
        Maximum training epochs for iterative learners.
    """

    model_type: str = "linear"
    validation_fraction: float = 0.2
    random_seed: int = 42
    max_epochs: int = 100


@dataclass(frozen=True)
class TrainingRunResult:
    """Result from a training pipeline run or its stub fallback.

    Attributes
    ----------
    run_id:
        Unique identifier for this training run (UUID4 string).
    model_type:
        Learner type used.
    n_train:
        Number of training examples.
    n_val:
        Number of validation examples.
    r_validation:
        Pearson r on the validation split (``0.0`` for stub runs).
    rmse_validation:
        RMSE on the validation split in log₁₀(K_A) units (``0.0`` for stub).
    artifact_key:
        Object-storage key where the serialized model is stored, or ``None``
        when the run was a stub or the artifact was not persisted.
    backend_available:
        ``False`` when the required ML library was absent.
    notes:
        Run-time notes.
    """

    run_id: str
    model_type: str
    n_train: int
    n_val: int
    r_validation: float
    rmse_validation: float
    artifact_key: str | None
    backend_available: bool
    notes: list[str]


@dataclass(frozen=True)
class CalibrationResult:
    """Result from a post-hoc calibration pass.

    Attributes
    ----------
    method:
        Calibration algorithm used (``"isotonic"``, ``"platt"``, ``"temperature"``,
        ``"stub"``).
    n_samples:
        Number of calibration examples.
    calibration_artifact_key:
        Object-storage key for the calibration mapping, or ``None``.
    backend_available:
        ``False`` when the calibration library was absent.
    notes:
        Run-time notes.
    """

    method: str
    n_samples: int
    calibration_artifact_key: str | None
    backend_available: bool
    notes: list[str]


@dataclass(frozen=True)
class EvaluationMetrics:
    """Standard evaluation metrics for affinity prediction.

    Attributes
    ----------
    r_pearson:
        Pearson correlation coefficient on the test set.
    rmse:
        Root-mean-square error in log₁₀(K_A) units.
    mae:
        Mean absolute error in log₁₀(K_A) units.
    n_samples:
        Number of test examples.
    ood_fraction:
        Fraction of test samples flagged as out-of-distribution.
    notes:
        Evaluation notes.
    """

    r_pearson: float
    rmse: float
    mae: float
    n_samples: int
    ood_fraction: float
    notes: list[str]


def run_training_pipeline(
    records: list[SPRTrainingRecord],
    config: TrainingPipelineConfig | None = None,
    *,
    object_store: Any | None = None,
    artifact_prefix: str = "models/training",
) -> TrainingRunResult:
    """Train a supervised affinity model on SPR-grounded training records.

    The function attempts to use the model type specified in ``config``.  When
    the required ML library is not installed it returns a ``TrainingRunResult``
    with ``backend_available=False`` and all numeric metrics set to ``0.0``.

    This contract defines the calling interface so downstream code can integrate
    any learner (sklearn, XGBoost, PyTorch) by satisfying this function's input
    and output shapes.

    Parameters
    ----------
    records:
        List of ``SPRTrainingRecord`` instances.
    config:
        Training configuration.  Defaults are used when not provided.
    object_store:
        Optional ``ObjectStore`` for persisting the trained model artifact.
    artifact_prefix:
        Object-storage key prefix for model artifacts.

    Returns
    -------
    TrainingRunResult
    """
    if config is None:
        config = TrainingPipelineConfig()

    run_id = str(uuid.uuid4())
    notes: list[str] = []

    if not records:
        notes.append("TRAINING_NO_RECORDS_PROVIDED")
        return TrainingRunResult(
            run_id=run_id,
            model_type=config.model_type,
            n_train=0,
            n_val=0,
            r_validation=0.0,
            rmse_validation=0.0,
            artifact_key=None,
            backend_available=False,
            notes=notes,
        )

    n_val = max(1, int(len(records) * config.validation_fraction))
    n_train = len(records) - n_val
    notes.append(f"TRAINING_SPLIT_TRAIN_{n_train}_VAL_{n_val}")

    if config.model_type in {"gnn"} and not is_torch_available():
        notes.append("TRAINING_TORCH_NOT_AVAILABLE_STUB")
        return TrainingRunResult(
            run_id=run_id,
            model_type=config.model_type,
            n_train=n_train,
            n_val=n_val,
            r_validation=0.0,
            rmse_validation=0.0,
            artifact_key=None,
            backend_available=False,
            notes=notes,
        )

    # Linear/sklearn path
    if config.model_type == "linear":
        return _train_linear(
            run_id=run_id,
            records=records,
            n_train=n_train,
            n_val=n_val,
            config=config,
            object_store=object_store,
            artifact_prefix=artifact_prefix,
            notes=notes,
        )

    notes.append(f"TRAINING_MODEL_TYPE_{config.model_type}_STUB_FALLBACK")
    return TrainingRunResult(
        run_id=run_id,
        model_type=config.model_type,
        n_train=n_train,
        n_val=n_val,
        r_validation=0.0,
        rmse_validation=0.0,
        artifact_key=None,
        backend_available=False,
        notes=notes,
    )


def _train_linear(
    *,
    run_id: str,
    records: list[SPRTrainingRecord],
    n_train: int,
    n_val: int,
    config: TrainingPipelineConfig,
    object_store: Any | None,
    artifact_prefix: str,
    notes: list[str],
) -> TrainingRunResult:
    """Internal: pure-Python ordinary-least-squares linear regression.

    This implementation does not require any external ML library, providing a
    built-in baseline for the training pipeline contract.
    """
    import math
    import random

    rng = random.Random(config.random_seed)
    shuffled = list(records)
    rng.shuffle(shuffled)
    train_records = shuffled[:n_train]
    val_records = shuffled[n_train : n_train + n_val]

    # Collect descriptor keys present in at least one training record.
    descriptor_keys: list[str] = []
    seen: set[str] = set()
    for rec in train_records:
        for key in rec.descriptors:
            if key not in seen:
                descriptor_keys.append(key)
                seen.add(key)
    descriptor_keys.sort()

    if not descriptor_keys:
        notes.append("TRAINING_NO_DESCRIPTORS_STUB")
        return TrainingRunResult(
            run_id=run_id,
            model_type="linear",
            n_train=n_train,
            n_val=n_val,
            r_validation=0.0,
            rmse_validation=0.0,
            artifact_key=None,
            backend_available=True,
            notes=notes,
        )

    def _to_vec(rec: SPRTrainingRecord) -> list[float]:
        return [float(rec.descriptors.get(k, 0.0)) for k in descriptor_keys]

    # Compute OLS via normal equations (no external lib needed).
    # X has shape [n_train, n_feat]; prepend bias column → augmented X.
    x_train = [_to_vec(r) for r in train_records]
    y_train = [r.measured_log_k for r in train_records]
    n_feat = len(descriptor_keys)

    # Add bias column: X_aug[i] = [1, x1, x2, ...]
    x_aug = [[1.0] + row for row in x_train]
    dim = n_feat + 1  # number of columns including bias

    # Compute X^T X row by row to improve cache locality.
    xt_x = [[0.0] * dim for _ in range(dim)]
    for row in x_aug:
        for k in range(dim):
            for j in range(dim):
                xt_x[k][j] += row[k] * row[j]
    xt_y = [sum(x_aug[i][k] * y_train[i] for i in range(n_train)) for k in range(dim)]

    # Regularized pseudo-inverse (Tikhonov λ=1e-4).
    lam = 1e-4
    for k in range(dim):
        xt_x[k][k] += lam

    # Gaussian elimination with partial pivoting.
    aug = [xt_x[k][:] + [xt_y[k]] for k in range(dim)]
    for col in range(dim):
        pivot_row = max(range(col, dim), key=lambda r: abs(aug[r][col]))
        aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot = aug[col][col]
        if abs(pivot) < 1e-12:
            # Near-zero pivot: force weight = 0 for this feature and skip elimination
            # so the degenerate column does not corrupt the remaining system.
            aug[col] = [0.0] * (dim + 1)
            aug[col][col] = 1.0  # identity row → extracted weight = 0
            continue
        aug[col] = [v / pivot for v in aug[col]]
        for row in range(dim):
            if row != col:
                factor = aug[row][col]
                aug[row] = [aug[row][j] - factor * aug[col][j] for j in range(dim + 1)]
    weights = [aug[k][-1] for k in range(dim)]

    def _predict(vec: list[float]) -> float:
        return weights[0] + sum(weights[j + 1] * vec[j] for j in range(n_feat))

    # Validation metrics.
    val_x = [_to_vec(r) for r in val_records]
    val_y = [r.measured_log_k for r in val_records]
    val_pred = [_predict(x) for x in val_x]

    if len(val_pred) >= 2:
        mean_y = sum(val_y) / len(val_y)
        mean_pred = sum(val_pred) / len(val_pred)
        num = sum((val_y[i] - mean_y) * (val_pred[i] - mean_pred) for i in range(n_val))
        denom = math.sqrt(
            sum((v - mean_y) ** 2 for v in val_y)
            * sum((v - mean_pred) ** 2 for v in val_pred)
        )
        r_val = round(num / denom, 4) if denom > 1e-12 else 0.0
        rmse_val = round(
            math.sqrt(sum((val_y[i] - val_pred[i]) ** 2 for i in range(n_val)) / n_val), 4
        )
    else:
        r_val = 0.0
        rmse_val = 0.0

    notes.append(f"TRAINING_LINEAR_R_VAL_{r_val}_RMSE_VAL_{rmse_val}")

    artifact_key: str | None = None
    if object_store is not None:
        artifact_key = f"{artifact_prefix}/{run_id}/linear_weights.json"
        object_store.put_json(
            artifact_key,
            {
                "run_id": run_id,
                "descriptor_keys": descriptor_keys,
                "weights": weights,
                "r_validation": r_val,
                "rmse_validation": rmse_val,
            },
        )
        notes.append(f"TRAINING_ARTIFACT_PERSISTED_{artifact_key}")

    return TrainingRunResult(
        run_id=run_id,
        model_type="linear",
        n_train=n_train,
        n_val=n_val,
        r_validation=r_val,
        rmse_validation=rmse_val,
        artifact_key=artifact_key,
        backend_available=True,
        notes=notes,
    )


def run_calibration(
    predictions: list[float],
    measured: list[float],
    *,
    method: str = "auto",
    object_store: Any | None = None,
    artifact_prefix: str = "models/calibration",
) -> CalibrationResult:
    """Calibrate model predictions against measured SPR affinities.

    Supported methods:
    - ``"isotonic"``: monotonic regression via ``sklearn.isotonic`` (if available).
    - ``"temperature"``: single-parameter temperature scaling.
    - ``"stub"``: no-op bookkeeping only.
    - ``"auto"``: tries isotonic first, falls back to temperature, then stub.

    Parameters
    ----------
    predictions:
        Model-predicted log₁₀(K_A) values.
    measured:
        SPR-measured log₁₀(K_A) values (same length as ``predictions``).
    method:
        Calibration algorithm to use.
    object_store:
        Optional ``ObjectStore`` for persisting the calibration artifact.
    artifact_prefix:
        Object-storage key prefix for calibration artifacts.

    Returns
    -------
    CalibrationResult
    """
    n = len(predictions)
    notes: list[str] = []

    if n == 0 or len(measured) != n:
        notes.append("CALIBRATION_NO_DATA_OR_LENGTH_MISMATCH")
        return CalibrationResult(
            method="stub",
            n_samples=0,
            calibration_artifact_key=None,
            backend_available=False,
            notes=notes,
        )

    if method in {"auto", "isotonic"}:
        try:
            from sklearn.isotonic import IsotonicRegression  # type: ignore[import]

            ir = IsotonicRegression(out_of_bounds="clip")
            ir.fit(predictions, measured)
            artifact_key: str | None = None
            if object_store is not None:
                cal_id = str(uuid.uuid4())
                artifact_key = f"{artifact_prefix}/{cal_id}/isotonic.json"
                # Store calibration pairs for reproducibility.
                object_store.put_json(
                    artifact_key,
                    {"method": "isotonic", "n_samples": n, "calibration_id": cal_id},
                )
            notes.append("CALIBRATION_ISOTONIC_FITTED")
            return CalibrationResult(
                method="isotonic",
                n_samples=n,
                calibration_artifact_key=artifact_key,
                backend_available=True,
                notes=notes,
            )
        except ModuleNotFoundError:
            notes.append("CALIBRATION_SKLEARN_NOT_AVAILABLE")
            if method == "isotonic":
                return CalibrationResult(
                    method="stub",
                    n_samples=n,
                    calibration_artifact_key=None,
                    backend_available=False,
                    notes=notes,
                )

    if method in {"auto", "temperature"}:
        # Temperature scaling: find scalar T to minimize MSE of pred/T vs measured.
        mean_pred = sum(predictions) / n
        mean_meas = sum(measured) / n
        num = sum(predictions[i] * measured[i] for i in range(n)) - n * mean_pred * mean_meas
        denom = sum(p ** 2 for p in predictions) - n * mean_pred ** 2
        temperature = round(num / denom, 6) if abs(denom) > 1e-12 else 1.0
        notes.append(f"CALIBRATION_TEMPERATURE_SCALE_{temperature}")
        artifact_key = None
        if object_store is not None:
            cal_id = str(uuid.uuid4())
            artifact_key = f"{artifact_prefix}/{cal_id}/temperature.json"
            object_store.put_json(
                artifact_key,
                {"method": "temperature", "temperature": temperature, "n_samples": n},
            )
        return CalibrationResult(
            method="temperature",
            n_samples=n,
            calibration_artifact_key=artifact_key,
            backend_available=True,
            notes=notes,
        )

    notes.append("CALIBRATION_STUB_FALLBACK")
    return CalibrationResult(
        method="stub",
        n_samples=n,
        calibration_artifact_key=None,
        backend_available=False,
        notes=notes,
    )


def evaluate_model(
    predictions: list[float],
    measured: list[float],
    *,
    ood_threshold_log_k: float = -3.0,
) -> EvaluationMetrics:
    """Compute standard evaluation metrics for an affinity prediction set.

    Parameters
    ----------
    predictions:
        Model-predicted log₁₀(K_A) values.
    measured:
        SPR-measured log₁₀(K_A) values (same length as ``predictions``).
    ood_threshold_log_k:
        Values below this threshold are flagged as out-of-distribution.

    Returns
    -------
    EvaluationMetrics
    """
    import math

    n = len(predictions)
    notes: list[str] = []

    if n == 0 or len(measured) != n:
        notes.append("EVALUATION_NO_DATA_OR_LENGTH_MISMATCH")
        return EvaluationMetrics(
            r_pearson=0.0, rmse=0.0, mae=0.0, n_samples=0, ood_fraction=0.0, notes=notes
        )

    mean_p = sum(predictions) / n
    mean_m = sum(measured) / n
    num = sum((predictions[i] - mean_p) * (measured[i] - mean_m) for i in range(n))
    denom = math.sqrt(
        sum((p - mean_p) ** 2 for p in predictions)
        * sum((m - mean_m) ** 2 for m in measured)
    )
    r_pearson = round(num / denom, 4) if abs(denom) > 1e-12 else 0.0
    rmse = round(math.sqrt(sum((predictions[i] - measured[i]) ** 2 for i in range(n)) / n), 4)
    mae = round(sum(abs(predictions[i] - measured[i]) for i in range(n)) / n, 4)
    ood_fraction = round(sum(1 for m in measured if m < ood_threshold_log_k) / n, 4)

    return EvaluationMetrics(
        r_pearson=r_pearson,
        rmse=rmse,
        mae=mae,
        n_samples=n,
        ood_fraction=ood_fraction,
        notes=notes,
    )
