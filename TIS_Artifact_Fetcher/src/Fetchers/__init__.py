"""TIS Artifact Fetcher - Uses Api/TISClient for all HTTP operations.

This module provides the ArtifactFetcher class for fetching artifacts from TIS
and producing JSON output compatible with ExcelHandler.

Classes:
    ArtifactFetcher: Fetches artifacts using recursive BFS search
"""

import datetime
import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import config
from Api import TISClient
from Filters import ArtifactFilter
from Utils import VersionParser, convert_ticks_to_iso

from config import (
    TIS_URL,
    DEBUG_MODE,
    LOG_LEVEL,
    get_json_prefix,
    get_latest_json_prefix,
    VW_XCU_PROJECT_ID,
    PATH_CONVENTIONS,
    COMPONENT_TYPE_FILTER,
    COMPONENT_NAME_FILTER,
    COMPONENT_GRP_FILTER,
    LIFE_CYCLE_STATUS_FILTER,
    SKIP_DELETED_ARTIFACTS,
    SKIP_FOLDER_PATTERNS,
    SKIP_PROJECTS,
    INCLUDE_PROJECTS,
    INCLUDE_SOFTWARE_LINES,
    CONCURRENT_REQUESTS as DEFAULT_CONCURRENT_REQUESTS,
    CHILDREN_LEVEL as DEFAULT_CHILDREN_LEVEL,
    RATE_LIMIT_DELAY as DEFAULT_RATE_LIMIT_DELAY,
)

logger = logging.getLogger(__name__)


class ArtifactFetcher:
    """
    TIS Artifact Fetcher using recursive BFS search.

    Uses Api/TISClient for all HTTP operations with:
    - Connection pooling
    - Response caching
    - Adaptive depth reduction
    - Concurrent requests

    Produces JSON output compatible with ExcelHandler.
    """

    def __init__(
        self,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        children_level: int = DEFAULT_CHILDREN_LEVEL,
        rate_limit_delay: float = DEFAULT_RATE_LIMIT_DELAY,
        enable_cache: bool = True,
        enable_pruning: bool = True,
        debug_mode: bool = DEBUG_MODE
    ):
        """
        Initialize the artifact extractor.

        Args:
            concurrent_requests: Max parallel API calls
            children_level: Depth to fetch at once
            rate_limit_delay: Delay between request batches
            enable_cache: Enable response caching
            enable_pruning: Enable smart branch pruning
            debug_mode: Enable debug output
        """
        self.concurrent_requests = concurrent_requests
        self.children_level = children_level
        self.rate_limit_delay = rate_limit_delay
        self.enable_cache = enable_cache
        self.enable_pruning = enable_pruning
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

        # Statistics
        self.branches_pruned = 0
        self.failed_components: List[str] = []

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

    def _extract_all_vveh_from_tree(
        self,
        data: Dict,
        current_path: List[str],
        results: List[Tuple[str, str, List[str], Dict]],
        _stats: Dict = None
    ) -> None:
        """Recursively extract all vVeh components from a fetched tree."""
        # Initialize stats on first call
        if _stats is None:
            _stats = {'visited': 0, 'with_attrs': 0, 'matches': 0}

        _stats['visited'] += 1

        component_id = data.get('rId')
        node_name = data.get('name', 'Unknown')
        full_path = current_path + [node_name]

        # Check component type filters
        component_type_name = data.get('componentType', {}).get('name')
        component_def_name = data.get('component', {}).get('name')
        component_grp_name = data.get('componentGrp', {}).get('name')
        attributes = data.get('attributes', [])

        if attributes:
            _stats['with_attrs'] += 1

        # Check each filter (None means filter is disabled)
        is_matching_type = COMPONENT_TYPE_FILTER is None or component_type_name in COMPONENT_TYPE_FILTER
        is_matching_component = COMPONENT_NAME_FILTER is None or component_def_name in COMPONENT_NAME_FILTER
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
                _stats['matches'] += 1
                results.append((component_id, node_name, full_path, data))

        # Process children
        children = data.get('children', [])
        for child in children:
            child_name = child.get('name', 'Unknown')
            if self._should_skip_folder(child_name):
                self.branches_pruned += 1
                continue
            self._extract_all_vveh_from_tree(child, full_path, results, _stats)

        # Log stats at root level
        if len(current_path) == 1:
            logger.debug(f"Tree scan: visited={_stats['visited']}, with_attrs={_stats['with_attrs']}, matches={_stats['matches']}")

    def _find_unexplored_leaves(
        self,
        data: Dict,
        current_path: List[str],
        fetch_depth: int = None
    ) -> List[Tuple[str, List[str]]]:
        """Find leaf nodes that might have unexplored children."""
        leaves = []
        effective_depth = fetch_depth if fetch_depth is not None else self.children_level

        if effective_depth == -1:
            return leaves

        def traverse(node: Dict, path: List[str], depth: int):
            children = node.get('children', [])
            node_name = node.get('name', 'Unknown')
            new_path = path + [node_name]

            if depth >= effective_depth - 1 and children:
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
    ) -> Tuple[List[Tuple[str, str, List[str], Dict]], Optional[Dict], int]:
        """Explore a leaf node for more artifacts."""
        results = []
        data, depth_used = self.client.get_component_adaptive(node_id)
        if not data:
            return results, None, depth_used

        self._extract_all_vveh_from_tree(data, current_path[:-1], results)
        return results, data, depth_used

    def _extract_artifact_info(
        self,
        component_data: Dict,
        component_path: str,
        component_id: str,
        version_parser: VersionParser
    ) -> Optional[Dict[str, Any]]:
        """Extract artifact information in the format expected by ExcelHandler.

        Fields are included based on component type:
        - vVeh_LCO: includes simulation_type, software_type, labcar_type, lco_version, vemox_version, is_genuine_build
        - test_ECU-TEST: includes test_type, test_type_path, test_type_mismatch, test_version, ecu_test_version
        """
        attributes = component_data.get('attributes', [])

        actual_component_type = component_data.get('componentType', {}).get('name', 'Unknown')
        actual_component_name = component_data.get('component', {}).get('name', 'Unknown')
        actual_component_grp = component_data.get('componentGrp', {}).get('name', 'Unknown')

        # Determine artifact type for field filtering
        is_vveh_lco = actual_component_name == 'vVeh_LCO'
        is_test_artifact = actual_component_name == 'test_ECU-TEST'

        # Common fields for all artifact types
        condensed = {
            'user': None,
            'life_cycle_status': None,
            'release_date_time': None,
            'created_date': None,
            'is_deleted': False,
            'deleted_date': None,
            'build_type': None
        }

        # vVeh_LCO specific fields
        if is_vveh_lco:
            condensed['simulation_type'] = self._extract_simulation_type(component_path)
            condensed['software_type'] = self._extract_software_type(component_path)
            condensed['labcar_type'] = self._extract_labcar_type(component_path)
            condensed['lco_version'] = None
            condensed['vemox_version'] = None
            condensed['is_genuine_build'] = None

        # test_ECU-TEST specific fields
        if is_test_artifact:
            condensed['test_type'] = None
            condensed['test_type_path'] = self._extract_test_type_from_path(component_path)
            condensed['test_type_mismatch'] = False
            condensed['test_version'] = None
            condensed['ecu_test_version'] = None
            condensed['test_configuration'] = None
            condensed['testbench_configuration'] = None

        # Extract created date from top-level component data
        created_ticks = component_data.get('created')
        if created_ticks:
            condensed['created_date'] = convert_ticks_to_iso(created_ticks)

        for attr in attributes:
            name = attr.get('name')
            value = attr.get('value')

            if not name or value is None:
                continue

            if name == 'user':
                condensed['user'] = value.lower() if value else value
            elif name == 'lifeCycleStatus':
                condensed['life_cycle_status'] = value
            elif name == 'releaseDateTime':
                condensed['release_date_time'] = convert_ticks_to_iso(value)
            elif name == 'tisFileDeletedDate':
                condensed['deleted_date'] = convert_ticks_to_iso(value)
                condensed['is_deleted'] = ArtifactFilter.is_artifact_deleted(attributes)
            # vVeh_LCO specific attribute extraction
            elif is_vveh_lco:
                if name == 'isGenuineBuild':
                    condensed['is_genuine_build'] = str(value).lower() == 'true'
                elif name == 'lcType':
                    if not condensed['labcar_type']:
                        condensed['labcar_type'] = value
                elif name == 'execution' and value:
                    condensed['lco_version'] = self._extract_lco_version(value)
                elif name == 'sources' and value:
                    condensed['vemox_version'] = self._extract_vemox_version(value, version_parser)
            # test_ECU-TEST specific attribute extraction
            elif is_test_artifact:
                if name == 'testType':
                    condensed['test_type'] = value
                elif name == 'testVersion':
                    condensed['test_version'] = value
                elif name == 'execution' and value:
                    condensed['ecu_test_version'] = self._extract_ecu_test_version(value)
                elif name == 'testConfiguration':
                    condensed['test_configuration'] = value
                elif name == 'testbenchConfiguration':
                    condensed['testbench_configuration'] = value

        # Build result with common fields
        result = {
            'name': component_data.get('name', 'Unknown'),
            'artifact_rid': component_id,
            'component_type': actual_component_name,
            'component_type_category': actual_component_type,
            'component_grp': actual_component_grp,
            'user': condensed['user'],
            'life_cycle_status': condensed['life_cycle_status'],
            'release_date_time': condensed['release_date_time'],
            'created_date': condensed['created_date'],
            'is_deleted': condensed['is_deleted'],
            'deleted_date': condensed['deleted_date'],
            'build_type': condensed['build_type'],
            'upload_path': component_path
        }

        # Add vVeh_LCO specific fields
        if is_vveh_lco:
            result['simulation_type'] = condensed['simulation_type']
            result['software_type'] = condensed['software_type']
            result['labcar_type'] = condensed['labcar_type']
            result['lco_version'] = condensed['lco_version']
            result['vemox_version'] = condensed['vemox_version']
            result['is_genuine_build'] = condensed['is_genuine_build']

        # Add test_ECU-TEST specific fields
        if is_test_artifact:
            result['test_type'] = condensed['test_type']
            result['test_type_path'] = condensed['test_type_path']
            result['test_type_mismatch'] = condensed['test_type_mismatch']
            result['test_version'] = condensed['test_version']
            result['ecu_test_version'] = condensed['ecu_test_version']
            result['test_configuration'] = condensed['test_configuration']
            result['testbench_configuration'] = condensed['testbench_configuration']

        return result

    def _extract_software_type(self, path: str) -> Optional[str]:
        """Extract software type (CSP/SWB) from path."""
        csp_swb_patterns = PATH_CONVENTIONS.get("vVeh_LCO", {}).get("CSP_SWB_contains", [])
        path_parts = path.split('/')
        for part in path_parts:
            for pattern in csp_swb_patterns:
                if pattern in part:
                    return part
        return None

    def _extract_labcar_type(self, path: str) -> Optional[str]:
        """Extract labcar type (VME/PCIe) from path."""
        labcar_types = PATH_CONVENTIONS.get("vVeh_LCO", {}).get("LabcarType", [])
        path_parts = path.split('/')
        for part in path_parts:
            if part in labcar_types:
                return part
        return None

    def _extract_simulation_type(self, path: str) -> Optional[str]:
        """Extract simulation type (HiL/SiL) from path."""
        if not path:
            return None
        path_parts = path.split('/')
        if 'HiL' in path_parts:
            return 'HiL'
        if 'SiL' in path_parts:
            return 'SiL'
        return None

    def _extract_test_type_from_path(self, path: str) -> Optional[str]:
        """Extract test type from path (directory under Test/{TestType})."""
        if not path:
            return None
        path_parts = path.split('/')
        # Look for 'Test' directory and return the next part
        for i, part in enumerate(path_parts):
            if part == 'Test' and i + 1 < len(path_parts):
                return path_parts[i + 1]
        return None

    def _extract_lco_version(self, execution_value: Any) -> Optional[str]:
        """Extract LCO version from execution data."""
        try:
            execution_data = json.loads(execution_value) if isinstance(execution_value, str) else execution_value
            if isinstance(execution_data, list):
                for dep in execution_data:
                    if isinstance(dep, dict) and dep.get('dependency') == 'LCO':
                        versions = dep.get('version', [])
                        if versions:
                            return versions[0]
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    def _extract_ecu_test_version(self, execution_value: Any) -> Optional[str]:
        """Extract ECU-TEST version from execution data."""
        try:
            execution_data = json.loads(execution_value) if isinstance(execution_value, str) else execution_value
            if isinstance(execution_data, list):
                for dep in execution_data:
                    if isinstance(dep, dict) and dep.get('dependency') == 'ECU-TEST':
                        versions = dep.get('version', [])
                        if versions:
                            return versions[0]
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    def _extract_vemox_version(self, sources_value: Any, version_parser: VersionParser) -> Optional[str]:
        """Extract VeMoX version from sources data."""
        try:
            sources_data = json.loads(sources_value) if isinstance(sources_value, str) else sources_value
            vemox_versions = version_parser.find_vemox_versions(sources_data)
            if vemox_versions:
                return vemox_versions[0]
        except (json.JSONDecodeError, AttributeError):
            pass
        return None

    def _process_software_line(
        self,
        sw_line_id: str,
        sw_line_name: str,
        project_name: str
    ) -> List[Dict[str, Any]]:
        """Process a software line using recursive BFS to find ALL artifacts."""
        artifacts = []
        version_parser = VersionParser()

        # Fetch with adaptive children level using TISClient
        data, depth_used = self.client.get_component_adaptive(sw_line_id)
        if not data:
            logger.warning(f"No data returned for software line '{sw_line_name}' (id={sw_line_id})")
            return artifacts

        children_count = len(data.get('children', []))
        logger.debug(f"Fetched '{sw_line_name}' at depth={depth_used}, {children_count} children")

        # Extract all vVeh candidates from the tree
        candidates: List[Tuple[str, str, List[str], Dict]] = []
        self._extract_all_vveh_from_tree(data, [project_name], candidates)

        # If tree wasn't deep enough, continue searching iteratively
        leaves_to_explore = self._find_unexplored_leaves(data, [project_name, sw_line_name], depth_used)

        iteration = 0
        while leaves_to_explore:
            iteration += 1
            total_leaves = len(leaves_to_explore)
            logger.info(f"  Iterative exploration [{iteration}]: {total_leaves} nodes to explore")

            new_leaves = []
            processed = 0

            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                futures = {}
                for leaf_id, leaf_path in leaves_to_explore:
                    future = executor.submit(self._explore_leaf_node, leaf_id, leaf_path)
                    futures[future] = (leaf_id, leaf_path)

                for future in as_completed(futures):
                    if self.cancel_event.is_set():
                        break
                    processed += 1
                    try:
                        leaf_results, leaf_data, leaf_depth = future.result()
                        candidates.extend(leaf_results)

                        if leaf_data and leaf_depth != -1:
                            leaf_id, leaf_path = futures[future]
                            more_leaves = self._find_unexplored_leaves(leaf_data, leaf_path, leaf_depth)
                            new_leaves.extend(more_leaves)

                        if processed % 10 == 0 or processed == total_leaves:
                            logger.info(f"    Progress: {processed}/{total_leaves} nodes, {len(candidates)} artifacts found")
                    except Exception as e:
                        logger.error(f"Error processing leaf: {e}")

                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)

            leaves_to_explore = new_leaves
            if new_leaves:
                logger.info(f"    Found {len(new_leaves)} more nodes at deeper level")

        # Process candidates into artifact format
        for comp_id, comp_name, path_list, comp_data in candidates:
            artifact_info = self._extract_artifact_info(
                comp_data, '/'.join(path_list), comp_id, version_parser
            )
            if artifact_info:
                artifacts.append(artifact_info)

        return artifacts

    def extract(self) -> Dict[str, Any]:
        """
        Extract artifacts from TIS using recursive search.

        Returns:
            Dict with structure: {project_name: {project_rid, software_lines: {...}}}
        """
        self.cancel_event.clear()
        self.branches_pruned = 0
        self.failed_components = []
        self.client.reset_statistics()
        self.client.clear_cache()

        structured_data = {}

        logger.info("=" * 60)
        logger.info("TIS ARTIFACT EXTRACTOR")
        logger.info("=" * 60)
        logger.info("Settings:")
        logger.info(f"  Concurrent requests: {self.concurrent_requests}")
        logger.info(f"  Children level: {self.children_level}")
        logger.info(f"  Cache enabled: {self.enable_cache}")
        logger.info(f"  Pruning enabled: {self.enable_pruning}")
        logger.info("=" * 60)

        # Get all projects
        projects_data, _, _ = self.client.get_component(VW_XCU_PROJECT_ID, children_level=1)
        if not projects_data:
            logger.error("Failed to get projects response")
            return structured_data

        projects = projects_data.get('children', [])
        total_projects = len(projects)
        logger.info(f"Found {total_projects} projects to process")

        if self.debug_mode:
            projects = projects[:1]
            logger.info("DEBUG MODE: Processing only the first project")

        for project_idx, project in enumerate(projects, 1):
            if self.cancel_event.is_set():
                logger.warning("Cancelled")
                break

            project_id = project.get('rId')
            project_name = project.get('name')

            if project_name in SKIP_PROJECTS:
                logger.debug(f"[{project_idx}/{total_projects}] Skipping project: {project_name}")
                continue

            if INCLUDE_PROJECTS and project_name not in INCLUDE_PROJECTS:
                logger.debug(f"[{project_idx}/{total_projects}] Skipping project: {project_name}")
                continue

            logger.info(f"[{project_idx}/{total_projects}] Processing project: {project_name}")

            project_response, _, _ = self.client.get_component(project_id, children_level=1)
            if not project_response:
                continue

            software_lines = project_response.get('children', [])
            logger.info(f"  Found {len(software_lines)} software lines")

            structured_data[project_name] = {
                'project_rid': project_id,
                'software_lines': {}
            }

            total_sw_lines = len(software_lines)
            processed_count = 0
            total_artifacts_in_project = 0

            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                futures = {}
                for sw_line in software_lines:
                    sw_line_id = sw_line.get('rId')
                    sw_line_name = sw_line.get('name')

                    if INCLUDE_SOFTWARE_LINES and sw_line_name not in INCLUDE_SOFTWARE_LINES:
                        continue

                    structured_data[project_name]['software_lines'][sw_line_name] = {
                        'software_line_rid': sw_line_id,
                        'artifacts': []
                    }

                    if sw_line_id:
                        future = executor.submit(
                            self._process_software_line,
                            sw_line_id,
                            sw_line_name,
                            project_name
                        )
                        futures[future] = sw_line_name

                for future in as_completed(futures):
                    if self.cancel_event.is_set():
                        break
                    try:
                        sw_artifacts = future.result()
                        sw_name = futures[future]
                        processed_count += 1
                        with self.results_lock:
                            structured_data[project_name]['software_lines'][sw_name]['artifacts'] = sw_artifacts
                            artifact_count = len(sw_artifacts) if sw_artifacts else 0
                            total_artifacts_in_project += artifact_count
                            logger.info(f"    [{processed_count}/{total_sw_lines}] {sw_name}: {artifact_count} artifacts")
                    except Exception as e:
                        processed_count += 1
                        logger.error(f"    [{processed_count}/{total_sw_lines}] Error processing: {e}")

            logger.info(f"  -> Project complete: {total_artifacts_in_project} total artifacts found")

            if self.rate_limit_delay > 0:
                time.sleep(self.rate_limit_delay)

        self._print_statistics()
        return structured_data

    def _print_statistics(self) -> None:
        """Log extraction statistics."""
        stats = self.client.get_statistics()
        logger.info("=== Extraction Statistics ===")
        logger.info(f"API Calls: {stats['api_calls_made']}, Cache Hits: {stats['cache_hits']}, Branches Pruned: {self.branches_pruned}")
        logger.info(f"Timeout Retries: {stats['timeout_retries']}, Depth Reductions: {stats['depth_reductions']}, Failed: {len(self.failed_components)}")
        if stats['api_calls_made'] > 0:
            logger.info(f"Cache Efficiency: {stats['cache_efficiency']:.1f}%")

    def cancel(self) -> None:
        """Cancel the extraction operation."""
        self.cancel_event.set()


def extract_latest_artifacts(structured_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract the latest artifact (highest rId) for each software line.

    Args:
        structured_data: Output from ArtifactFetcher.extract()

    Returns:
        Dict with latest_artifact for each software line
    """
    latest_artifacts = {}

    for project_name, project_data in structured_data.items():
        project_rid = project_data['project_rid']
        latest_artifacts[project_name] = {
            'project_rid': project_rid,
            'software_lines': {}
        }

        for sw_line_name, sw_line_data in project_data['software_lines'].items():
            sw_line_rid = sw_line_data['software_line_rid']
            artifacts = sw_line_data['artifacts']

            if artifacts:
                latest_artifact = max(artifacts, key=lambda x: int(x['artifact_rid']))
                latest_artifacts[project_name]['software_lines'][sw_line_name] = {
                    'software_line_rid': sw_line_rid,
                    'latest_artifact': latest_artifact
                }
            else:
                latest_artifacts[project_name]['software_lines'][sw_line_name] = {
                    'software_line_rid': sw_line_rid,
                    'latest_artifact': None
                }

    return latest_artifacts


def separate_by_component_type(structured_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Separate artifacts by component_type into separate data structures.

    Args:
        structured_data: Output from ArtifactFetcher.extract()

    Returns:
        Dict keyed by component_type, each containing the same structure as input
        but only with artifacts of that component_type
    """
    by_component = {}

    for project_name, project_data in structured_data.items():
        project_rid = project_data['project_rid']

        for sw_line_name, sw_line_data in project_data['software_lines'].items():
            sw_line_rid = sw_line_data['software_line_rid']
            artifacts = sw_line_data.get('artifacts', [])

            for artifact in artifacts:
                comp_type = artifact.get('component_type', 'unknown')

                # Initialize structure for this component type if needed
                if comp_type not in by_component:
                    by_component[comp_type] = {}

                if project_name not in by_component[comp_type]:
                    by_component[comp_type][project_name] = {
                        'project_rid': project_rid,
                        'software_lines': {}
                    }

                if sw_line_name not in by_component[comp_type][project_name]['software_lines']:
                    by_component[comp_type][project_name]['software_lines'][sw_line_name] = {
                        'software_line_rid': sw_line_rid,
                        'artifacts': []
                    }

                by_component[comp_type][project_name]['software_lines'][sw_line_name]['artifacts'].append(artifact)

    return by_component


def save_results(structured_data: Dict, output_dir: Path = None) -> Path:
    """Save the structured data to a JSON file with timestamp (legacy single file)."""
    if output_dir is None:
        if not config.CURRENT_RUN_DIR:
            raise ValueError("Run directory not configured!")
        output_dir = config.CURRENT_RUN_DIR

    output_file = output_dir / f"{get_json_prefix()}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    logger.info(f"Saving results to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(structured_data, f, indent=2, default=str)
    logger.info("Results successfully saved")

    return output_file


def save_results_by_component_type(structured_data: Dict, output_dir: Path = None) -> Dict[str, Path]:
    """
    Save artifacts separated by component_type to individual JSON files.

    Args:
        structured_data: Output from ArtifactFetcher.extract()
        output_dir: Output directory (defaults to config.CURRENT_RUN_DIR)

    Returns:
        Dict mapping component_type to output file path
    """
    if output_dir is None:
        if not config.CURRENT_RUN_DIR:
            raise ValueError("Run directory not configured!")
        output_dir = config.CURRENT_RUN_DIR

    # Separate by component type
    by_component = separate_by_component_type(structured_data)

    output_files = {}
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    for comp_type, comp_data in by_component.items():
        # Create filename from component type (sanitize for filesystem, preserve case)
        safe_name = comp_type.replace(' ', '_')
        output_file = output_dir / f"{safe_name}_artifacts_{timestamp}.json"

        # Count artifacts
        artifact_count = sum(
            len(sw['artifacts'])
            for proj in comp_data.values()
            for sw in proj['software_lines'].values()
        )

        logger.info(f"Saving {artifact_count} {comp_type} artifacts to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(comp_data, f, indent=2, default=str)

        output_files[comp_type] = output_file

    return output_files


def save_latest_artifacts(latest_artifacts: Dict[str, Any], output_dir: Path = None) -> Path:
    """Save the latest artifacts data to a JSON file."""
    if output_dir is None:
        if not config.CURRENT_RUN_DIR:
            raise ValueError("Run directory not configured!")
        output_dir = config.CURRENT_RUN_DIR

    output_file = output_dir / f"{get_latest_json_prefix()}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    logger.info(f"Saving latest artifacts to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(latest_artifacts, f, indent=2, default=str)
    logger.info("Latest artifacts successfully saved")

    return output_file


def save_latest_artifacts_by_component_type(structured_data: Dict[str, Any], output_dir: Path = None) -> Dict[str, Path]:
    """
    Save latest artifacts separated by component_type to individual JSON files.

    Args:
        structured_data: Output from ArtifactFetcher.extract()
        output_dir: Output directory (defaults to config.CURRENT_RUN_DIR)

    Returns:
        Dict mapping component_type to output file path
    """
    if output_dir is None:
        if not config.CURRENT_RUN_DIR:
            raise ValueError("Run directory not configured!")
        output_dir = config.CURRENT_RUN_DIR

    # First separate by component type
    by_component = separate_by_component_type(structured_data)

    output_files = {}
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')

    for comp_type, comp_data in by_component.items():
        # Extract latest artifacts for this component type
        latest_for_type = extract_latest_artifacts(comp_data)

        # Create filename from component type (sanitize for filesystem, preserve case)
        safe_name = comp_type.replace(' ', '_')
        output_file = output_dir / f"latest_{safe_name}_artifacts_{timestamp}.json"

        # Count latest artifacts
        artifact_count = sum(
            1 for proj in latest_for_type.values()
            for sw in proj['software_lines'].values()
            if sw.get('latest_artifact') is not None
        )

        logger.info(f"Saving {artifact_count} latest {comp_type} artifacts to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(latest_for_type, f, indent=2, default=str)

        output_files[comp_type] = output_file

    return output_files


def run_extraction() -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Main function to run artifact extraction.

    This is a convenience function that replaces the old tis_artifact_extractor.main()

    Returns:
        Tuple of (success: bool, structured_data: Dict or None)
    """
    try:
        if not config.CURRENT_RUN_DIR or not isinstance(config.CURRENT_RUN_DIR, Path):
            raise ValueError("Run directory not properly configured!")

        extractor = ArtifactFetcher()
        structured_data = extractor.extract()

        if not structured_data:
            logger.error("No data extracted!")
            return False, None

        # Save artifacts separated by component type
        output_files = save_results_by_component_type(structured_data)
        logger.info(f"Saved {len(output_files)} component type files: {list(output_files.keys())}")

        # Save latest artifacts separated by component type
        latest_output_files = save_latest_artifacts_by_component_type(structured_data)
        logger.info(f"Saved {len(latest_output_files)} latest artifact files: {list(latest_output_files.keys())}")

        # Print summary
        by_component = separate_by_component_type(structured_data)
        for comp_type, comp_data in by_component.items():
            latest_for_type = extract_latest_artifacts(comp_data)
            count = sum(
                1 for p in latest_for_type.values()
                for sw in p['software_lines'].values()
                if sw.get('latest_artifact') is not None
            )
            logger.info(f"  {comp_type}: {count} software lines with artifacts")

        logger.info("=" * 60)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 60)

        return True, structured_data

    except Exception as e:
        logger.error(f"Error in TIS artifact extraction: {e}")
        import traceback
        traceback.print_exc()
        return False, None
