"""Data models for TIS artifact extraction and mapping.

This module defines dataclasses for structured data throughout the application,
replacing the use of untyped dictionaries.

Classes:
    LifeCycleStatus: Enum for artifact lifecycle status values
    DeviationType: Enum for path/naming deviation types
    ArtifactInfo: TIS artifact with all metadata
    SoftwareLine: Software line with its artifacts
    Project: TIS project containing software lines
    MappingEntry: Mapping between Excel software line and TIS data
    ValidationResult: Result of artifact path/naming validation
    ValidationReport: Aggregated validation report for multiple artifacts
    ExtractionStatistics: Statistics from artifact extraction process
    APIResponse: Wrapper for TIS API response data
    RunContext: Context for a single execution run
    ValidatedArtifact: Validated artifact with deviation tracking
    Checkpoint: Checkpoint for resume capability in validation runs
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any, Set
from enum import Enum


class LifeCycleStatus(Enum):
    """Lifecycle status values for TIS artifacts."""
    RELEASED = "released"
    ARCHIVED = "archived"
    DEVELOPMENT = "development"
    UNKNOWN = "unknown"

    @classmethod
    def from_string(cls, value: Optional[str]) -> "LifeCycleStatus":
        """Convert string to LifeCycleStatus enum."""
        if not value:
            return cls.UNKNOWN
        try:
            return cls(value.lower())
        except ValueError:
            return cls.UNKNOWN


class DeviationType(Enum):
    """Types of path/naming deviations for validation."""
    VALID = "VALID"
    # Path deviations
    MISSING_MODEL = "MISSING_MODEL"
    MISSING_HIL = "MISSING_HIL"
    MISSING_SIL = "MISSING_SIL"
    MISSING_CSP_SWB = "MISSING_CSP_SWB"
    CSP_SWB_UNDER_MODEL = "CSP_SWB_UNDER_MODEL"
    WRONG_LOCATION = "WRONG_LOCATION"
    INVALID_SUBFOLDER = "INVALID_SUBFOLDER"
    # Naming deviations
    INVALID_NAME_FORMAT = "INVALID_NAME_FORMAT"
    NAME_MISMATCH = "NAME_MISMATCH"


@dataclass
class ArtifactInfo:
    """Represents a TIS artifact with all its metadata."""
    name: str
    artifact_rid: str
    component_type: Optional[str] = None
    component_type_category: Optional[str] = None
    component_grp: Optional[str] = None
    simulation_type: Optional[str] = None
    software_type: Optional[str] = None
    labcar_type: Optional[str] = None
    test_type: Optional[str] = None
    user: Optional[str] = None
    lco_version: Optional[str] = None
    vemox_version: Optional[str] = None
    is_genuine_build: Optional[bool] = None
    life_cycle_status: Optional[str] = None
    release_date_time: Optional[str] = None
    created_date: Optional[str] = None
    is_deleted: bool = False
    deleted_date: Optional[str] = None
    build_type: Optional[str] = None
    upload_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'artifact_rid': self.artifact_rid,
            'component_type': self.component_type,
            'component_type_category': self.component_type_category,
            'component_grp': self.component_grp,
            'simulation_type': self.simulation_type,
            'software_type': self.software_type,
            'labcar_type': self.labcar_type,
            'test_type': self.test_type,
            'user': self.user,
            'lco_version': self.lco_version,
            'vemox_version': self.vemox_version,
            'is_genuine_build': self.is_genuine_build,
            'life_cycle_status': self.life_cycle_status,
            'release_date_time': self.release_date_time,
            'created_date': self.created_date,
            'is_deleted': self.is_deleted,
            'deleted_date': self.deleted_date,
            'build_type': self.build_type,
            'upload_path': self.upload_path
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactInfo":
        """Create ArtifactInfo from dictionary."""
        return cls(
            name=data.get('name', 'Unknown'),
            artifact_rid=data.get('artifact_rid', ''),
            component_type=data.get('component_type'),
            component_type_category=data.get('component_type_category'),
            component_grp=data.get('component_grp'),
            simulation_type=data.get('simulation_type'),
            software_type=data.get('software_type'),
            labcar_type=data.get('labcar_type'),
            test_type=data.get('test_type'),
            user=data.get('user'),
            lco_version=data.get('lco_version'),
            vemox_version=data.get('vemox_version'),
            is_genuine_build=data.get('is_genuine_build'),
            life_cycle_status=data.get('life_cycle_status'),
            release_date_time=data.get('release_date_time'),
            created_date=data.get('created_date'),
            is_deleted=data.get('is_deleted', False),
            deleted_date=data.get('deleted_date'),
            build_type=data.get('build_type'),
            upload_path=data.get('upload_path', '')
        )


@dataclass
class SoftwareLine:
    """Represents a software line with its artifacts."""
    name: str
    software_line_rid: str
    artifacts: List[ArtifactInfo] = field(default_factory=list)
    latest_artifact: Optional[ArtifactInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'software_line_rid': self.software_line_rid,
            'artifacts': [a.to_dict() for a in self.artifacts],
            'latest_artifact': self.latest_artifact.to_dict() if self.latest_artifact else None
        }


@dataclass
class Project:
    """Represents a TIS project containing software lines."""
    name: str
    project_rid: str
    software_lines: Dict[str, SoftwareLine] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'project_rid': self.project_rid,
            'software_lines': {
                name: sw_line.to_dict() for name, sw_line in self.software_lines.items()
            }
        }


@dataclass
class MappingEntry:
    """Represents a mapping between an Excel software line and TIS data."""
    software_line: str
    project: Optional[str] = None
    project_rid: Optional[str] = None
    found: bool = False
    software_line_rid: Optional[str] = None
    latest_artifact: Optional[ArtifactInfo] = None
    matched_with: Optional[str] = None
    ecu_hw_variante: str = ""
    project_class: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for report generation."""
        return {
            'project': self.project,
            'project_rid': self.project_rid,
            'found': self.found,
            'software_line_rid': self.software_line_rid,
            'latest_artifact': self.latest_artifact.to_dict() if self.latest_artifact else None,
            'matched_with': self.matched_with,
            'master_data': {
                'ECU - HW Variante': self.ecu_hw_variante,
                'Project class': self.project_class
            }
        }


@dataclass
class ValidationResult:
    """Result of artifact path/naming validation."""
    artifact_rid: str
    artifact_name: str
    path: str
    user: str
    tis_link: str
    deviation_type: DeviationType = DeviationType.VALID
    deviation_details: str = ""
    expected_path_hint: str = ""
    name_pattern_matched: Optional[str] = None
    name_pattern_groups: Optional[Dict[str, str]] = None

    @property
    def is_valid(self) -> bool:
        """Check if the artifact passed validation."""
        return self.deviation_type == DeviationType.VALID

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for report generation."""
        return {
            'component_id': self.artifact_rid,
            'component_name': self.artifact_name,
            'path': self.path,
            'user': self.user,
            'tis_link': self.tis_link,
            'deviation_type': self.deviation_type.value,
            'deviation_details': self.deviation_details,
            'expected_path_hint': self.expected_path_hint,
            'name_pattern_matched': self.name_pattern_matched,
            'name_pattern_groups': self.name_pattern_groups
        }


@dataclass
class ValidationReport:
    """Aggregated validation report for multiple artifacts."""
    timestamp: str = ""
    total_projects: int = 0
    processed_projects: int = 0
    total_artifacts_found: int = 0
    valid_artifacts: int = 0
    deviations_found: int = 0
    # Performance metrics (used by optimized validator)
    total_api_calls: int = 0
    total_time_seconds: float = 0.0
    cache_hits: int = 0
    branches_pruned: int = 0
    depth_reductions: int = 0
    timeout_retries: int = 0
    # Results collections
    valid_paths: List[Dict[str, Any]] = field(default_factory=list)
    deviations: List[Dict[str, Any]] = field(default_factory=list)
    deviations_by_type: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    deviations_by_user: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    deviations_by_project: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    failed_projects: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


@dataclass
class ExtractionStatistics:
    """Statistics from artifact extraction process."""
    api_calls_made: int = 0
    cache_hits: int = 0
    branches_pruned: int = 0
    depth_reductions: int = 0
    timeout_retries: int = 0
    failed_components: List[str] = field(default_factory=list)

    @property
    def cache_efficiency(self) -> float:
        """Calculate cache hit efficiency percentage."""
        total = self.api_calls_made + self.cache_hits
        if total == 0:
            return 0.0
        return (self.cache_hits / total) * 100


@dataclass
class APIResponse:
    """Wrapper for TIS API response data."""
    data: Optional[Dict[str, Any]]
    timed_out: bool
    elapsed_time: float
    from_cache: bool = False

    @property
    def success(self) -> bool:
        """Check if the API call was successful."""
        return self.data is not None and not self.timed_out


@dataclass
class RunContext:
    """Context for a single execution run, replacing global mutable state."""
    run_dir: Optional[str] = None
    output_dir: Optional[str] = None
    excel_copy_path: Optional[str] = None
    start_time: Optional[datetime] = None

    @property
    def is_initialized(self) -> bool:
        """Check if context is properly initialized."""
        return self.run_dir is not None and self.output_dir is not None


@dataclass
class ValidatedArtifact:
    """Information about a validated artifact with deviation tracking."""
    component_id: str
    component_name: str
    path: str
    component_type: str
    user: Optional[str] = None
    upload_date: Optional[str] = None
    life_cycle_status: Optional[str] = None
    is_deleted: bool = False
    deleted_date: Optional[str] = None
    deviation_type: DeviationType = DeviationType.VALID
    deviation_details: str = ""
    expected_path_hint: str = ""
    tis_link: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result['deviation_type'] = self.deviation_type.value
        return result


@dataclass
class Checkpoint:
    """Checkpoint for resume capability in validation runs."""
    timestamp: str
    processed_project_ids: Set[str]
    artifacts_found: List[Dict[str, Any]]
    last_project_index: int
