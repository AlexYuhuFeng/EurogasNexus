"""Research data foundation for semantic point-in-time datasets.

This package owns semantics, temporal truth, provenance, and dataset
definitions. Model training infrastructure remains downstream.
"""

from eurogas_nexus.domain.research.capabilities import (
    REGISTERED_RESEARCH_CAPABILITIES,
    CapabilityContract,
)
from eurogas_nexus.domain.research.datasets import (
    DatasetBuildResult,
    DatasetMode,
    DatasetSpec,
    DatasetSplit,
    DatasetSplitType,
    build_dataset,
)
from eurogas_nexus.domain.research.export import export_csv, export_parquet
from eurogas_nexus.domain.research.features import (
    FeatureAvailabilityClass,
    FeatureDefinition,
)
from eurogas_nexus.domain.research.ontology import (
    ONTOLOGY_SCHEMA_VERSION,
    CanonicalEntityType,
    OntologyConcept,
    canonical_entity_id,
)
from eurogas_nexus.domain.research.resampling import (
    ResamplingPolicy,
    bounded_resample,
)
from eurogas_nexus.domain.research.series import (
    MetricType,
    SeriesDefinition,
    TemporalSeriesType,
)
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import (
    DatasetPointInTimePolicy,
    ObservationKind,
    TemporalIntegrityState,
    as_of_eligible,
    effective_available_at,
    forecast_vintage_at,
)
from eurogas_nexus.domain.research.units import UnitConversion, convert_value

__all__ = [
    "CapabilityContract",
    "CanonicalEntityType",
    "DatasetBuildResult",
    "DatasetMode",
    "DatasetPointInTimePolicy",
    "DatasetSpec",
    "DatasetSplit",
    "DatasetSplitType",
    "FeatureAvailabilityClass",
    "FeatureDefinition",
    "MetricType",
    "ObservationKind",
    "ONTOLOGY_SCHEMA_VERSION",
    "REGISTERED_RESEARCH_CAPABILITIES",
    "OntologyConcept",
    "ResamplingPolicy",
    "SeriesDefinition",
    "TargetDefinition",
    "TargetKind",
    "TemporalIntegrityState",
    "TemporalSeriesType",
    "UnitConversion",
    "as_of_eligible",
    "export_csv",
    "export_parquet",
    "bounded_resample",
    "build_dataset",
    "canonical_entity_id",
    "convert_value",
    "effective_available_at",
    "forecast_vintage_at",
]
