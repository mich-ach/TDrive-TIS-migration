"""Path and naming validation for TIS artifacts.

This module provides classes and functions to validate artifact paths against
expected conventions and naming patterns.

Classes:
    PathValidator: Validates artifact paths against expected conventions
    OptimizedArtifactValidator: High-performance recursive artifact finder

Functions:
    validate_path_simple: Simple path validation without component-specific logic
"""

import datetime
import json
import logging
import pickle
import re
import threading
import time
from typing import Tuple, List, Dict, Optional, Any, Callable, Set
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from Api import TISClient
from Models import DeviationType, ValidationReport, ValidatedArtifact, Checkpoint
from Filters import ArtifactFilter
from Reports import generate_excel_report

from config import (
    TIS_URL,
    PATH_CONVENTION_ENABLED,
    PATH_EXPECTED_STRUCTURE,
    PATH_MODEL_SUBFOLDERS,
    PATH_VALID_SUBFOLDERS_HIL,
    NAMING_CONVENTION_ENABLED,
    NAMING_CONVENTION_PATTERNS,
    SKIP_FOLDER_PATTERNS,
    SKIP_DELETED_ARTIFACTS,
    TIS_LINK_TEMPLATE,
    DEBUG_MODE,
    COMPONENT_TYPE_FILTER,
    COMPONENT_NAME_FILTER,
    COMPONENT_GRP_FILTER,
    LIFE_CYCLE_STATUS_FILTER,
    CONCURRENT_REQUESTS as DEFAULT_CONCURRENT_REQUESTS,
    CHILDREN_LEVEL as DEFAULT_CHILDREN_LEVEL,
    RATE_LIMIT_DELAY as DEFAULT_RATE_LIMIT_DELAY,
)

logger = logging.getLogger(__name__)

# Expected path patterns
CSP_SWB_PATTERN = re.compile(r"(CSP|SWB)", re.IGNORECASE)

# Checkpoint interval
CHECKPOINT_INTERVAL = 50


class PathValidator:
    """Validates artifact paths against expected conventions."""

    def __init__(self):
        """Initialize the path validator with compiled naming patterns."""
        self._compiled_patterns = self._compile_naming_patterns()

    def _compile_naming_patterns(self) -> Dict:
        """Compile naming convention patterns from config."""
        compiled = {}
        if NAMING_CONVENTION_ENABLED and NAMING_CONVENTION_PATTERNS:
            for pattern_name, pattern_config in NAMING_CONVENTION_PATTERNS.items():
                try:
                    compiled[pattern_name] = {
                        'regex': re.compile(pattern_config['pattern']),
                        'description': pattern_config.get('description', ''),
                        'example': pattern_config.get('example', '')
                    }
                except re.error as e:
                    logger.warning(f"Invalid regex for pattern '{pattern_name}': {e}")
        return compiled

    def validate_path(
        self,
        path: str,
        artifact_name: str = None,
        component_name: str = None
    ) -> Tuple[DeviationType, str, str]:
        """
        Validate artifact path against expected convention.

        Args:
            path: The artifact's path (e.g., "Project/SWLine/Model/HiL/CSP/...")
            artifact_name: The artifact's name (for naming validation)
            component_name: The component type name (for component-specific validation)

        Returns:
            Tuple of (DeviationType, details, expected_path_hint)
        """
        if not PATH_CONVENTION_ENABLED:
            return (DeviationType.VALID, "", "")

        path_parts = path.split('/') if path else []

        if len(path_parts) < 2:
            return (
                DeviationType.WRONG_LOCATION,
                "Path too short",
                "[Project]/[SWLine]/Model/HiL|SiL/[subfolder]/..."
            )

        project = path_parts[0]
        sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

        if 'Model' not in path_parts:
            return (
                DeviationType.MISSING_MODEL,
                "Artifact not under 'Model' folder",
                f"{project}/{sw_line}/Model/..."
            )

        model_index = path_parts.index('Model')
        remaining = path_parts[model_index + 1:]

        is_hil_path = 'HiL' in remaining
        is_sil_path = 'SiL' in remaining

        expected_structure = self._get_expected_structure(component_name)
        model_subfolders = self._get_model_subfolders(component_name)

        if not is_hil_path and not is_sil_path:
            if remaining and any(sf in remaining[0] for sf in PATH_VALID_SUBFOLDERS_HIL):
                return (
                    DeviationType.CSP_SWB_UNDER_MODEL,
                    f"{remaining[0]} directly under Model (missing HiL)",
                    f"{project}/{sw_line}/Model/HiL/{remaining[0]}/..."
                )
            return (
                DeviationType.MISSING_HIL,
                "Missing 'HiL' or 'SiL' folder after Model",
                expected_structure or f"{project}/{sw_line}/Model/HiL|SiL/[subfolder]/..."
            )

        if is_hil_path:
            result = self._validate_hil_path(
                remaining, project, sw_line, expected_structure, model_subfolders
            )
            if result[0] != DeviationType.VALID:
                return result

        if is_sil_path:
            result = self._validate_sil_path(
                remaining, project, sw_line, expected_structure, model_subfolders
            )
            if result[0] != DeviationType.VALID:
                return result

        return (DeviationType.VALID, "", "")

    def _validate_hil_path(
        self,
        remaining: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        model_subfolders: List[str]
    ) -> Tuple[DeviationType, str, str]:
        """Validate HiL path structure."""
        hil_index = remaining.index('HiL')
        after_hil = remaining[hil_index + 1:]

        if not after_hil:
            return (
                DeviationType.MISSING_CSP_SWB,
                "Missing subfolder after HiL",
                expected_structure or f"{project}/{sw_line}/Model/HiL/[CSP|SWB]/..."
            )

        first_after_hil = after_hil[0]
        check_subfolders = model_subfolders if model_subfolders else PATH_VALID_SUBFOLDERS_HIL
        is_valid_subfolder = any(
            sf.lower() in first_after_hil.lower()
            for sf in check_subfolders
        )
        if not is_valid_subfolder:
            return (
                DeviationType.INVALID_SUBFOLDER,
                f"Invalid subfolder '{first_after_hil}' after HiL",
                expected_structure or f"{project}/{sw_line}/Model/HiL/[{'/'.join(check_subfolders)}]/..."
            )

        return (DeviationType.VALID, "", "")

    def _validate_sil_path(
        self,
        remaining: List[str],
        project: str,
        sw_line: str,
        expected_structure: str,
        model_subfolders: List[str]
    ) -> Tuple[DeviationType, str, str]:
        """Validate SiL path structure."""
        sil_index = remaining.index('SiL')
        after_sil = remaining[sil_index + 1:]

        if not after_sil:
            return (
                DeviationType.MISSING_SIL,
                "Missing subfolder after SiL",
                expected_structure or f"{project}/{sw_line}/Model/SiL/[subfolder]/..."
            )

        if model_subfolders:
            first_after_sil = after_sil[0]
            is_valid_subfolder = any(
                sf.lower() in first_after_sil.lower()
                for sf in model_subfolders
            )
            if not is_valid_subfolder:
                return (
                    DeviationType.INVALID_SUBFOLDER,
                    f"Invalid subfolder '{first_after_sil}' after SiL (expected: {', '.join(model_subfolders)})",
                    expected_structure or f"{project}/{sw_line}/Model/SiL/[{'/'.join(model_subfolders)}]/..."
                )

        return (DeviationType.VALID, "", "")

    def _get_model_subfolders(self, component_name: str) -> List[str]:
        """Get expected model subfolders for a component_name by matching patterns."""
        if not component_name:
            return []

        if component_name in PATH_MODEL_SUBFOLDERS:
            return PATH_MODEL_SUBFOLDERS[component_name]

        for pattern, subfolders in PATH_MODEL_SUBFOLDERS.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return subfolders

        if 'MDL' in component_name and 'SiL' not in component_name:
            return PATH_VALID_SUBFOLDERS_HIL

        return []

    def _get_expected_structure(self, component_name: str) -> str:
        """Get expected path structure for a component_name."""
        if not component_name:
            return ""

        if component_name in PATH_EXPECTED_STRUCTURE:
            return PATH_EXPECTED_STRUCTURE[component_name]

        for pattern, structure in PATH_EXPECTED_STRUCTURE.items():
            if pattern.startswith('_comment'):
                continue
            if component_name.startswith(pattern):
                return structure

        return ""

    def validate_naming_convention(
        self,
        artifact_name: str
    ) -> Tuple[bool, Optional[str], Optional[Dict], Optional[str]]:
        """
        Validate artifact name against configured patterns.

        Args:
            artifact_name: The artifact's name to validate

        Returns:
            Tuple of (is_valid, matched_pattern_name, matched_groups, error_message)
        """
        if not NAMING_CONVENTION_ENABLED or not self._compiled_patterns:
            return (True, None, None, None)

        for pattern_name, pattern_data in self._compiled_patterns.items():
            match = pattern_data['regex'].match(artifact_name)
            if match:
                return (True, pattern_name, match.groupdict(), None)

        return (False, None, None, "Name does not match any known pattern")


def validate_path_simple(path: str) -> Tuple[DeviationType, str, str]:
    """
    Simple path validation without component-specific logic.

    This is a standalone function for use without PathValidator instance.

    Args:
        path: The artifact's path

    Returns:
        Tuple of (DeviationType, details, expected_path_hint)
    """
    path_parts = path.split('/')

    if len(path_parts) < 2:
        return (
            DeviationType.WRONG_LOCATION,
            "Path too short",
            "[Project]/[SWLine]/Model/HiL/[CSP|SWB]/..."
        )

    project_name = path_parts[0]
    sw_line = path_parts[1] if len(path_parts) > 1 else "Unknown"

    if 'Model' not in path_parts:
        return (
            DeviationType.MISSING_MODEL,
            "Artifact not under 'Model' folder",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    model_index = path_parts.index('Model')
    remaining_after_model = path_parts[model_index + 1:]

    if 'HiL' not in remaining_after_model:
        if remaining_after_model and CSP_SWB_PATTERN.search(remaining_after_model[0]):
            return (
                DeviationType.CSP_SWB_UNDER_MODEL,
                "CSP/SWB directly under Model (missing HiL)",
                f"{project_name}/{sw_line}/Model/HiL/{remaining_after_model[0]}/..."
            )
        return (
            DeviationType.MISSING_HIL,
            "Missing 'HiL' folder after Model",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    hil_index = remaining_after_model.index('HiL')
    remaining_after_hil = remaining_after_model[hil_index + 1:]

    if not remaining_after_hil or not CSP_SWB_PATTERN.search(remaining_after_hil[0]):
        return (
            DeviationType.MISSING_CSP_SWB,
            "Missing CSP/SWB folder after HiL",
            f"{project_name}/{sw_line}/Model/HiL/[CSP|SWB]/..."
        )

    return (DeviationType.VALID, "", "")


class OptimizedArtifactValidator:
    """
    High-performance artifact validator with multiple optimizations.

    Uses Api/TISClient for all HTTP operations with:
    - Connection pooling
    - Response caching
    - Adaptive depth reduction
    - Concurrent requests
    """

    def __init__(
        self,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        children_level: int = DEFAULT_CHILDREN_LEVEL,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
        enable_cache: bool = True,
        enable_pruning: bool = True,
        checkpoint_dir: Optional[Path] = None,
        debug_mode: bool = DEBUG_MODE
    ):
        """
        Initialize the optimized validator.

        Args:
            concurrent_requests: Max parallel API calls (default: 5)
            children_level: Depth to fetch at once (default: 3)
            rate_limit_delay: Delay between request batches (default: 0.05s)
            enable_cache: Enable response caching (default: True)
            enable_pruning: Enable smart branch pruning (default: True)
            checkpoint_dir: Directory for checkpoint files (default: None)
            debug_mode: Enable debug output (default: from config)
        """
        self.concurrent_requests = concurrent_requests
        self.children_level = children_level
        self.rate_limit_delay = rate_limit_delay
        self.enable_cache = enable_cache
        self.enable_pruning = enable_pruning
        self.checkpoint_dir = checkpoint_dir or Path('.')
        self.debug_mode = debug_mode

        # Initialize TISClient for all HTTP operations
        self.client = TISClient(
            concurrent_requests=concurrent_requests,
            children_level=children_level,
            enable_cache=enable_cache,
            debug_mode=debug_mode
        )

        # Threading
        self.cancel_event = threading.Event()
        self.results_lock = threading.Lock()

        # Statistics (some come from client)
        self.branches_pruned = 0
        self._progress_callback = None

        # Results
        self.artifacts_found: List[ValidatedArtifact] = []
        self.report = ValidationReport()

        # Compile skip patterns
        self._skip_patterns = [re.compile(p, re.IGNORECASE) for p in SKIP_FOLDER_PATTERNS]

    def _should_skip_folder(self, folder_name: str) -> bool:
        """Determine if a folder should be skipped based on naming patterns."""
        if not self.enable_pruning:
            return False

        for pattern in self._skip_patterns:
            if pattern.match(folder_name):
                return True
        return False

    def _extract_all_components_from_tree(
        self,
        data: Dict,
        current_path: List[str],
        results: List[Tuple[str, str, List[str], Dict]]
    ) -> None:
        """Recursively extract all components from a fetched tree."""
        component_id = data.get('rId')
        node_name = data.get('name', 'Unknown')
        full_path = current_path + [node_name]

        # Check if this component is an artifact candidate
        component_type_name = data.get('componentType', {}).get('name')
        component_def_name = data.get('component', {}).get('name')
        component_grp_name = data.get('componentGrp', {}).get('name')
        attributes = data.get('attributes', [])

        # Check each filter (None means filter is disabled)
        is_matching_type = COMPONENT_TYPE_FILTER is None or component_type_name == COMPONENT_TYPE_FILTER
        is_matching_component = COMPONENT_NAME_FILTER is None or component_def_name == COMPONENT_NAME_FILTER
        is_matching_grp = COMPONENT_GRP_FILTER is None or component_grp_name == COMPONENT_GRP_FILTER

        if is_matching_type and is_matching_component and is_matching_grp and attributes:
            has_artifact = any(attr.get('name') == 'artifact' for attr in attributes)
            is_deleted = ArtifactFilter.is_artifact_deleted(attributes)
            life_cycle_status = ArtifactFilter.get_life_cycle_status(attributes)

            is_matching_status = (
                not LIFE_CYCLE_STATUS_FILTER or
                life_cycle_status in LIFE_CYCLE_STATUS_FILTER
            )

            if (has_artifact and
                (not SKIP_DELETED_ARTIFACTS or not is_deleted) and
                is_matching_status):
                results.append((component_id, node_name, full_path, data))

        # Process children
        for child in data.get('children', []):
            child_name = child.get('name', 'Unknown')

            if self._should_skip_folder(child_name):
                self.branches_pruned += 1
                continue

            self._extract_all_components_from_tree(child, full_path, results)

    def _process_artifact_candidate(
        self,
        component_id: str,
        component_name: str,
        path_list: List[str],
        data: Dict
    ) -> Optional[ValidatedArtifact]:
        """Process a potential artifact and extract details."""
        path = '/'.join(path_list)
        attributes = data.get('attributes', [])

        artifact = ValidatedArtifact(
            component_id=component_id,
            component_name=component_name,
            path=path,
            component_type="vVeh",
            tis_link=TIS_LINK_TEMPLATE.format(component_id)
        )

        # Extract attributes
        for attr in attributes:
            attr_name = attr.get('name')
            attr_value = attr.get('value')

            if attr_name == 'user':
                artifact.user = attr_value
            elif attr_name == 'lifeCycleStatus':
                artifact.life_cycle_status = attr_value
            elif attr_name == 'tisFileDeletedDate' and attr_value:
                artifact.is_deleted = True
                artifact.deleted_date = attr_value

        # Validate path
        deviation_type, details, hint = validate_path_simple(path)
        artifact.deviation_type = deviation_type
        artifact.deviation_details = details
        artifact.expected_path_hint = hint

        return artifact

    def _process_software_line_concurrent(
        self,
        sw_line_id: str,
        sw_line_name: str,
        project_name: str
    ) -> List[ValidatedArtifact]:
        """Process a software line using optimized concurrent approach."""
        artifacts = []

        # Fetch with adaptive children level using TISClient
        data, depth_used = self.client.get_component_adaptive(sw_line_id)
        if not data:
            return artifacts

        if self.debug_mode:
            logger.debug(f"Fetched {sw_line_name} at depth {depth_used}")

        # Extract all artifact candidates from the tree
        candidates: List[Tuple[str, str, List[str], Dict]] = []
        self._extract_all_components_from_tree(data, [project_name], candidates)

        # Process candidates
        for comp_id, comp_name, path_list, comp_data in candidates:
            artifact = self._process_artifact_candidate(comp_id, comp_name, path_list, comp_data)
            if artifact:
                artifacts.append(artifact)

        # If tree wasn't deep enough, explore leaves
        leaves_to_explore = self._find_unexplored_leaves(data, [project_name, sw_line_name])

        if leaves_to_explore:
            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                futures = {}
                for leaf_id, leaf_path in leaves_to_explore:
                    future = executor.submit(self._explore_leaf_node, leaf_id, leaf_path)
                    futures[future] = (leaf_id, leaf_path)

                for future in as_completed(futures):
                    if self.cancel_event.is_set():
                        break
                    try:
                        leaf_artifacts = future.result()
                        artifacts.extend(leaf_artifacts)
                    except Exception as e:
                        if self.debug_mode:
                            logger.error(f"Error processing leaf: {e}")

                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)

        return artifacts

    def _find_unexplored_leaves(
        self,
        data: Dict,
        current_path: List[str]
    ) -> List[Tuple[str, List[str]]]:
        """Find leaf nodes that might have unexplored children."""
        leaves = []

        def traverse(node: Dict, path: List[str], depth: int):
            children = node.get('children', [])
            node_name = node.get('name', 'Unknown')
            new_path = path + [node_name]

            if depth >= self.children_level - 1 and children:
                for child in children:
                    child_name = child.get('name', '')
                    if not self._should_skip_folder(child_name):
                        child_id = child.get('rId')
                        if child_id:
                            leaves.append((child_id, new_path + [child_name]))
            else:
                for child in children:
                    child_name = child.get('name', '')
                    if not self._should_skip_folder(child_name):
                        traverse(child, new_path, depth + 1)

        traverse(data, current_path[:-1], 0)
        return leaves

    def _explore_leaf_node(
        self,
        node_id: str,
        current_path: List[str]
    ) -> List[ValidatedArtifact]:
        """Explore a leaf node for more artifacts using adaptive depth."""
        artifacts = []

        data, _ = self.client.get_component_adaptive(node_id)
        if not data:
            return artifacts

        candidates: List[Tuple[str, str, List[str], Dict]] = []
        self._extract_all_components_from_tree(data, current_path[:-1], candidates)

        for comp_id, comp_name, path_list, comp_data in candidates:
            artifact = self._process_artifact_candidate(comp_id, comp_name, path_list, comp_data)
            if artifact:
                artifacts.append(artifact)

        return artifacts

    def _save_checkpoint(self, processed_ids: Set[str], project_index: int) -> None:
        """Save checkpoint for resume capability."""
        checkpoint = Checkpoint(
            timestamp=datetime.datetime.now().isoformat(),
            processed_project_ids=processed_ids,
            artifacts_found=[a.to_dict() for a in self.artifacts_found],
            last_project_index=project_index
        )

        checkpoint_file = self.checkpoint_dir / "validation_checkpoint.pkl"
        with open(checkpoint_file, 'wb') as f:
            pickle.dump(checkpoint, f)

        if self.debug_mode:
            logger.debug(f"Checkpoint saved: {len(processed_ids)} projects processed")

    def _load_checkpoint(self) -> Optional[Checkpoint]:
        """Load checkpoint if exists."""
        checkpoint_file = self.checkpoint_dir / "validation_checkpoint.pkl"
        if checkpoint_file.exists():
            try:
                with open(checkpoint_file, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Could not load checkpoint: {e}")
        return None

    def run_validation(self, resume: bool = False) -> ValidationReport:
        """
        Run validation with all optimizations enabled.

        Args:
            resume: If True, resume from last checkpoint
        """
        overall_start_time = time.time()
        self.cancel_event.clear()
        self.artifacts_found = []
        self.branches_pruned = 0
        self.client.reset_statistics()
        self.client.clear_cache()

        self.report = ValidationReport(
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        processed_project_ids: Set[str] = set()
        start_index = 0

        if resume:
            checkpoint = self._load_checkpoint()
            if checkpoint:
                processed_project_ids = checkpoint.processed_project_ids
                start_index = checkpoint.last_project_index
                logger.info(f"Resuming from checkpoint: {len(processed_project_ids)} projects already processed")

        try:
            logger.info("=" * 60)
            logger.info("OPTIMIZED ARTIFACT STRUCTURE VALIDATOR")
            logger.info("=" * 60)
            logger.info("Settings:")
            logger.info(f"  Concurrent requests: {self.concurrent_requests}")
            logger.info(f"  Children level: {self.children_level}")
            logger.info(f"  Cache enabled: {self.enable_cache}")
            logger.info(f"  Pruning enabled: {self.enable_pruning}")
            logger.info("=" * 60)

            # Fetch projects
            projects_data, _, _ = self.client.get_component("790066", children_level=1)

            if not projects_data:
                logger.error("Failed to fetch projects")
                return self.report

            project_list = projects_data.get('children', [])
            self.report.total_projects = len(project_list)

            logger.info(f"Found {self.report.total_projects} projects")

            for project_idx, project in enumerate(project_list[start_index:], start_index + 1):
                if self.cancel_event.is_set():
                    logger.warning("Cancelled")
                    break

                project_id = project.get('rId')
                project_name = project.get('name', 'Unknown')

                if project_id in processed_project_ids:
                    continue

                logger.info(f"[{project_idx}/{self.report.total_projects}] Processing: {project_name}")

                try:
                    project_data, _, _ = self.client.get_component(project_id, children_level=1)

                    if not project_data:
                        self.report.failed_projects.append({
                            'project_id': project_id,
                            'project_name': project_name,
                            'error': 'Failed to fetch'
                        })
                        continue

                    software_lines = project_data.get('children', [])
                    logger.info(f"  Software lines: {len(software_lines)}")

                    with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                        futures = {}
                        for sw_line in software_lines:
                            sw_id = sw_line.get('rId')
                            sw_name = sw_line.get('name', 'Unknown')

                            if sw_id:
                                future = executor.submit(
                                    self._process_software_line_concurrent,
                                    sw_id,
                                    sw_name,
                                    project_name
                                )
                                futures[future] = sw_name

                        for future in as_completed(futures):
                            if self.cancel_event.is_set():
                                break
                            try:
                                sw_artifacts = future.result()
                                with self.results_lock:
                                    self.artifacts_found.extend(sw_artifacts)
                                    if sw_artifacts:
                                        logger.info(f"    Found {len(sw_artifacts)} artifacts in {futures[future]}")
                            except Exception as e:
                                if self.debug_mode:
                                    logger.error(f"    Error: {e}")

                    processed_project_ids.add(project_id)
                    self.report.processed_projects += 1

                    if project_idx % CHECKPOINT_INTERVAL == 0:
                        self._save_checkpoint(processed_project_ids, project_idx)

                except Exception as e:
                    logger.error(f"  Error: {e}")
                    self.report.failed_projects.append({
                        'project_id': project_id,
                        'project_name': project_name,
                        'error': str(e)
                    })

                if self._progress_callback:
                    self._progress_callback(project_idx, self.report.total_projects)

                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)

            self._compile_report(overall_start_time)
            return self.report

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise

    def _compile_report(self, start_time: float) -> None:
        """Compile final report."""
        stats = self.client.get_statistics()

        self.report.total_time_seconds = time.time() - start_time
        self.report.total_api_calls = stats['api_calls_made']
        self.report.cache_hits = stats['cache_hits']
        self.report.branches_pruned = self.branches_pruned
        self.report.depth_reductions = stats['depth_reductions']
        self.report.timeout_retries = stats['timeout_retries']
        self.report.total_artifacts_found = len(self.artifacts_found)

        for dev_type in DeviationType:
            self.report.deviations_by_type[dev_type.value] = []

        for artifact in self.artifacts_found:
            artifact_dict = artifact.to_dict()

            if artifact.deviation_type == DeviationType.VALID:
                self.report.valid_artifacts += 1
                self.report.valid_paths.append(artifact_dict)
            else:
                self.report.deviations_found += 1
                self.report.deviations.append(artifact_dict)

                self.report.deviations_by_type[artifact.deviation_type.value].append(artifact_dict)

                user = artifact.user or "UNKNOWN"
                if user not in self.report.deviations_by_user:
                    self.report.deviations_by_user[user] = []
                self.report.deviations_by_user[user].append(artifact_dict)

                project_name = artifact.path.split('/')[0] if artifact.path else "Unknown"
                if project_name not in self.report.deviations_by_project:
                    self.report.deviations_by_project[project_name] = []
                self.report.deviations_by_project[project_name].append(artifact_dict)

    def print_summary(self) -> None:
        """Log optimization statistics and results summary."""
        stats = self.client.get_statistics()

        logger.info("=" * 60)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 60)

        logger.info("Performance Metrics:")
        logger.info(f"  Runtime: {self.report.total_time_seconds:.1f}s")
        logger.info(f"  API Calls: {self.report.total_api_calls}")
        logger.info(f"  Cache Hits: {self.report.cache_hits}")
        logger.info(f"  Branches Pruned: {self.report.branches_pruned}")

        if self.report.total_api_calls > 0:
            efficiency = self.report.cache_hits / (self.report.total_api_calls + self.report.cache_hits) * 100
            logger.info(f"  Cache Efficiency: {efficiency:.1f}%")

        logger.info("Adaptive Depth Statistics:")
        logger.info(f"  Timeout Retries: {self.report.timeout_retries}")
        logger.info(f"  Depth Reductions: {self.report.depth_reductions}")
        if stats['components_with_reduced_depth'] > 0:
            logger.info(f"  Components with Reduced Depth: {stats['components_with_reduced_depth']}")

        logger.info("Results:")
        logger.info(f"  Projects Processed: {self.report.processed_projects}/{self.report.total_projects}")
        logger.info(f"  Artifacts Found: {self.report.total_artifacts_found}")
        logger.info(f"  Valid: {self.report.valid_artifacts}")
        logger.info(f"  Deviations: {self.report.deviations_found}")

        if self.report.deviations_by_user:
            logger.info("Top Uploaders with Deviations:")
            sorted_users = sorted(
                self.report.deviations_by_user.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )[:5]
            for user, devs in sorted_users:
                logger.info(f"  {user}: {len(devs)} deviations")

    def save_report(self, output_dir: Path) -> str:
        """Save report to JSON file."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        output_file = output_dir / f"optimized_validation_report_{timestamp}.json"

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.report.to_dict(), f, indent=2, default=str)

        logger.info(f"Report saved: {output_file}")
        return str(output_file)

    def generate_excel_report(self, output_dir: Path) -> str:
        """Generate Excel report with validation results."""
        return generate_excel_report(
            self.report,
            output_dir,
            component_depth_overrides=self.client.component_depth_overrides
        )

    def set_progress_callback(self, callback: Callable[[int, int], None]):
        """Set a callback function for progress updates."""
        self._progress_callback = callback

    def cancel_operation(self):
        """Cancel the current validation operation."""
        self.cancel_event.set()
