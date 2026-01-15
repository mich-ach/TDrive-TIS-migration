"""
Optimized Artifact Structure Validator - High-performance recursive artifact finder.

Optimizations implemented:
1. Combined API calls (children + attributes in one request)
2. Concurrent API requests with rate limiting (ThreadPoolExecutor)
3. Adaptive children level (fetch multiple levels at once)
4. Smart branch pruning (skip unlikely folders)
5. Response caching (LRU cache for repeated lookups)
6. Checkpoint/Resume capability
7. Connection pool tuning

Expected Convention:
    {Project}/{SoftwareLine}/Model/HiL/{CSP*|SWB*}/.../{vVeh artifact}
"""

import datetime
import json
import logging
import pickle
import re
import threading
import time
from typing import List, Dict, Any, Optional, Callable, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import ujson
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Import shared utilities and models
from datetime_utils import parse_ticks_to_datetime
from artifact_filter import ArtifactFilter
from models import DeviationType, ValidationReport, ValidatedArtifact, Checkpoint
from path_validator import validate_path_simple, CSP_SWB_PATTERN
from validation_excel_report import generate_excel_report

from config import (
    TIS_URL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_BACKOFF_FACTOR,
    API_RETRY_STATUS_CODES,
    CONCURRENT_REQUESTS as DEFAULT_CONCURRENT_REQUESTS,
    CHILDREN_LEVEL as DEFAULT_CHILDREN_LEVEL,
    RATE_LIMIT_DELAY as DEFAULT_RATE_LIMIT_DELAY,
    CACHE_MAX_SIZE,
    ADAPTIVE_TIMEOUT_THRESHOLD,
    MIN_CHILDREN_LEVEL,
    DEPTH_REDUCTION_STEP,
    SKIP_FOLDER_PATTERNS,
    SKIP_DELETED_ARTIFACTS,
    TIS_LINK_TEMPLATE,
    DEBUG_MODE,
    SLOW_MODE,
    API_WAIT_TIME,
    COMPONENT_TYPE_FILTER,
    COMPONENT_NAME_FILTER,
    COMPONENT_GRP_FILTER,
    LIFE_CYCLE_STATUS_FILTER,
)

# =============================================================================
# LOGGING SETUP
# =============================================================================

logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION (loaded from config.py/config.json)
# =============================================================================

CHECKPOINT_INTERVAL = 50             # Save checkpoint every N projects

# Note: CSP_SWB_PATTERN is imported from path_validator
# Note: DeviationType, ValidationReport, ValidatedArtifact, Checkpoint are imported from models


# =============================================================================
# OPTIMIZED VALIDATOR
# =============================================================================

class OptimizedArtifactValidator:
    """
    High-performance artifact validator with multiple optimizations.
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

        # Threading
        self.cancel_event = threading.Event()
        self.api_lock = threading.Lock()
        self.results_lock = threading.Lock()

        # Statistics
        self.api_calls_made = 0
        self.cache_hits = 0
        self.branches_pruned = 0
        self.depth_reductions = 0
        self.timeout_retries = 0
        self._progress_callback = None

        # Cache
        self._response_cache: Dict[str, Dict] = {}

        # Adaptive depth tracking - remember components that need lower depth
        self._component_depth_overrides: Dict[str, int] = {}

        # Results
        self.artifacts_found: List[ValidatedArtifact] = []
        self.report = ValidationReport()

        # Compile skip patterns
        self._skip_patterns = [re.compile(p, re.IGNORECASE) for p in SKIP_FOLDER_PATTERNS]

        # Session pool for concurrent requests
        self._session_local = threading.local()

    def _get_session(self) -> requests.Session:
        """Get thread-local session with connection pooling."""
        if not hasattr(self._session_local, 'session'):
            session = requests.Session()
            retry_strategy = Retry(
                total=API_MAX_RETRIES,
                backoff_factor=API_BACKOFF_FACTOR,
                status_forcelist=API_RETRY_STATUS_CODES,
                allowed_methods=["GET"]
            )
            # Increased pool size for concurrent requests
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=self.concurrent_requests,
                pool_maxsize=self.concurrent_requests * 2
            )
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._session_local.session = session
        return self._session_local.session

    def _make_api_request(
        self,
        url: str,
        use_cache: bool = True,
        timeout: Optional[Tuple[float, float]] = None
    ) -> Tuple[Optional[Dict], bool, float]:
        """
        Make API request with caching support.

        Args:
            url: The API URL to request
            use_cache: Whether to use caching
            timeout: Custom timeout tuple (connect, read), defaults to API_TIMEOUT

        Returns:
            Tuple of (response_data, timed_out, elapsed_time)
        """
        # Check cache first
        if use_cache and self.enable_cache and url in self._response_cache:
            with self.api_lock:
                self.cache_hits += 1
            return self._response_cache[url], False, 0.0

        request_timeout = timeout or API_TIMEOUT
        start_time = time.time()

        try:
            session = self._get_session()
            response = session.get(
                url,
                verify=True,
                timeout=request_timeout,
                headers={'Accept-Encoding': 'gzip, deflate'}
            )
            elapsed = time.time() - start_time
            response.raise_for_status()
            data = ujson.loads(response.content)

            with self.api_lock:
                self.api_calls_made += 1

            # Cache response
            if use_cache and self.enable_cache and len(self._response_cache) < CACHE_MAX_SIZE:
                self._response_cache[url] = data

            return data, False, elapsed

        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            if self.debug_mode:
                logger.warning(f"API request timed out after {elapsed:.1f}s: {url}")
            return None, True, elapsed

        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start_time
            if self.debug_mode:
                logger.warning(f"API read timeout after {elapsed:.1f}s: {url}")
            return None, True, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            if self.debug_mode:
                logger.error(f"API request failed after {elapsed:.1f}s: {url} - {e}")
            return None, False, elapsed

    def _should_skip_folder(self, folder_name: str) -> bool:
        """
        Determine if a folder should be skipped based on naming patterns.

        Optimization: Skip folders unlikely to contain artifacts.
        """
        if not self.enable_pruning:
            return False

        # Check skip patterns
        for pattern in self._skip_patterns:
            if pattern.match(folder_name):
                return True

        return False

    def _fetch_component_optimized(self, component_id: str) -> Tuple[Optional[Dict], int]:
        """
        Fetch component with children AND attributes using adaptive depth.

        If the request times out or takes too long (>5s), automatically
        reduces the children level and retries. Remembers components that
        need lower depth for future calls.

        Returns:
            Tuple of (response_data, depth_used)
        """
        # Check if we have a known depth override for this component
        current_depth = self._component_depth_overrides.get(component_id, self.children_level)

        while current_depth >= MIN_CHILDREN_LEVEL:
            url = f"{TIS_URL}{component_id}?mappingType=TCI&childrenlevel={current_depth}&attributes=true"

            # Use adaptive timeout based on depth
            adaptive_timeout = (5, ADAPTIVE_TIMEOUT_THRESHOLD + (current_depth * 2))

            data, timed_out, elapsed = self._make_api_request(url, timeout=adaptive_timeout)

            # Check if we got a response
            if data is not None:
                # If this was slower than threshold but succeeded, remember for future
                if elapsed > ADAPTIVE_TIMEOUT_THRESHOLD and current_depth > MIN_CHILDREN_LEVEL:
                    with self.api_lock:
                        # Store slightly lower depth for next time
                        self._component_depth_overrides[component_id] = max(
                            MIN_CHILDREN_LEVEL,
                            current_depth - DEPTH_REDUCTION_STEP
                        )
                    if self.debug_mode:
                        logger.debug(f"Slow component {component_id}: {elapsed:.1f}s at depth {current_depth}, will use depth {self._component_depth_overrides[component_id]} next time")
                return data, current_depth

            # If timed out or no response, reduce depth and retry
            if timed_out or elapsed > ADAPTIVE_TIMEOUT_THRESHOLD:
                with self.api_lock:
                    self.timeout_retries += 1

                new_depth = current_depth - DEPTH_REDUCTION_STEP

                if new_depth >= MIN_CHILDREN_LEVEL:
                    with self.api_lock:
                        self.depth_reductions += 1
                    logger.warning(f"Timeout: reducing depth {current_depth} -> {new_depth} for component {component_id}")

                    # Remember this component needs lower depth
                    self._component_depth_overrides[component_id] = new_depth
                    current_depth = new_depth
                else:
                    # Already at minimum depth, give up
                    logger.error(f"Failed: component {component_id} timed out at minimum depth")
                    return None, current_depth
            else:
                # Some other error, don't retry
                return None, current_depth

        return None, MIN_CHILDREN_LEVEL

    def _fetch_component_simple(self, component_id: str) -> Optional[Dict]:
        """
        Simple fetch without adaptive logic (for backward compatibility).
        Used where we don't need children.
        """
        url = f"{TIS_URL}{component_id}?mappingType=TCI&childrenlevel=1&attributes=true"
        data, _, _ = self._make_api_request(url)
        return data

    def _extract_all_components_from_tree(
        self,
        data: Dict,
        current_path: List[str],
        results: List[Tuple[str, str, List[str], Dict]]
    ) -> None:
        """
        Recursively extract all components from a fetched tree.

        Optimization: Process multiple levels from single API response.
        """
        component_id = data.get('rId')
        node_name = data.get('name', 'Unknown')
        full_path = current_path + [node_name]

        # Check if this component is an artifact candidate
        # Filters are optional - if set to null/None, that filter is disabled
        component_type_name = data.get('componentType', {}).get('name')  # e.g., "vVeh"
        component_def_name = data.get('component', {}).get('name')  # e.g., "vVeh_LCO"
        component_grp_name = data.get('componentGrp', {}).get('name')  # e.g., "TIS Artifact Container"
        attributes = data.get('attributes', [])

        # Check each filter (None means filter is disabled)
        is_matching_type = COMPONENT_TYPE_FILTER is None or component_type_name == COMPONENT_TYPE_FILTER
        is_matching_component = COMPONENT_NAME_FILTER is None or component_def_name == COMPONENT_NAME_FILTER
        is_matching_grp = COMPONENT_GRP_FILTER is None or component_grp_name == COMPONENT_GRP_FILTER

        if is_matching_type and is_matching_component and is_matching_grp and attributes:
            has_artifact = any(attr.get('name') == 'artifact' for attr in attributes)
            is_deleted = ArtifactFilter.is_artifact_deleted(attributes)
            life_cycle_status = ArtifactFilter.get_life_cycle_status(attributes)

            # Check lifeCycleStatus filter (None or empty list disables the filter)
            is_matching_status = (
                not LIFE_CYCLE_STATUS_FILTER or
                life_cycle_status in LIFE_CYCLE_STATUS_FILTER
            )

            # Include artifact if all conditions are met
            if (has_artifact and
                (not SKIP_DELETED_ARTIFACTS or not is_deleted) and
                is_matching_status):
                results.append((component_id, node_name, full_path, data))

        # Process children
        for child in data.get('children', []):
            child_name = child.get('name', 'Unknown')

            # Apply branch pruning
            if self._should_skip_folder(child_name):
                with self.api_lock:
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
        deviation_type, details, hint = self._validate_path_convention(path)
        artifact.deviation_type = deviation_type
        artifact.deviation_details = details
        artifact.expected_path_hint = hint

        return artifact

    def _validate_path_convention(self, path: str) -> Tuple[DeviationType, str, str]:
        """Validate artifact path against expected convention.

        Delegates to the shared validate_path_simple function from path_validator.
        """
        return validate_path_simple(path)

    def _process_software_line_concurrent(
        self,
        sw_line_id: str,
        sw_line_name: str,
        project_name: str
    ) -> List[ValidatedArtifact]:
        """
        Process a software line using optimized concurrent approach.

        Optimization: Fetch deep tree, extract all candidates, then validate.
        Uses adaptive depth to handle slow responses.
        """
        artifacts = []

        # Fetch with adaptive children level
        data, depth_used = self._fetch_component_optimized(sw_line_id)
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

        # If tree wasn't deep enough, we need to continue searching
        # Find leaf nodes that might have more children
        leaves_to_explore = self._find_unexplored_leaves(data, [project_name, sw_line_name])

        if leaves_to_explore:
            # Process remaining leaves concurrently
            with ThreadPoolExecutor(max_workers=self.concurrent_requests) as executor:
                futures = {}
                for leaf_id, leaf_path in leaves_to_explore:
                    future = executor.submit(
                        self._explore_leaf_node,
                        leaf_id,
                        leaf_path
                    )
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

                # Rate limiting between batches
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

            # If at max fetched depth and has children indicator, it's a leaf to explore
            if depth >= self.children_level - 1 and children:
                # Check if any child might have more children (heuristic)
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

        traverse(data, current_path[:-1], 0)  # Start from sw_line level
        return leaves

    def _explore_leaf_node(
        self,
        node_id: str,
        current_path: List[str]
    ) -> List[ValidatedArtifact]:
        """Explore a leaf node for more artifacts using adaptive depth."""
        artifacts = []

        data, _ = self._fetch_component_optimized(node_id)
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
        self.api_calls_made = 0
        self.cache_hits = 0
        self.branches_pruned = 0
        self._response_cache.clear()

        self.report = ValidationReport(
            timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        processed_project_ids: Set[str] = set()
        start_index = 0

        # Check for checkpoint
        if resume:
            checkpoint = self._load_checkpoint()
            if checkpoint:
                processed_project_ids = checkpoint.processed_project_ids
                start_index = checkpoint.last_project_index
                # Restore artifacts (would need to reconstruct ValidatedArtifact objects)
                logger.info(f"Resuming from checkpoint: {len(processed_project_ids)} projects already processed")

        try:
            logger.info("=" * 60)
            logger.info("OPTIMIZED ARTIFACT STRUCTURE VALIDATOR")
            logger.info("=" * 60)
            logger.info("Settings:")
            logger.info(f"  Concurrent requests: {self.concurrent_requests}")
            logger.info(f"  Children level: {self.children_level} (min: {MIN_CHILDREN_LEVEL})")
            logger.info(f"  Adaptive timeout: {ADAPTIVE_TIMEOUT_THRESHOLD}s")
            logger.info(f"  Cache enabled: {self.enable_cache}")
            logger.info(f"  Pruning enabled: {self.enable_pruning}")
            logger.info("=" * 60)

            # Fetch projects
            url = f"{TIS_URL}790066?mappingType=TCI&childrenlevel=1"
            projects_data, _, _ = self._make_api_request(url)

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

                # Skip already processed
                if project_id in processed_project_ids:
                    continue

                logger.info(f"[{project_idx}/{self.report.total_projects}] Processing: {project_name}")

                try:
                    # Get software lines
                    sw_url = f"{TIS_URL}{project_id}?mappingType=TCI&childrenlevel=1"
                    project_data, _, _ = self._make_api_request(sw_url)

                    if not project_data:
                        self.report.failed_projects.append({
                            'project_id': project_id,
                            'project_name': project_name,
                            'error': 'Failed to fetch'
                        })
                        continue

                    software_lines = project_data.get('children', [])
                    logger.info(f"  Software lines: {len(software_lines)}")

                    # Process software lines concurrently
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

                    # Checkpoint
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

                # Rate limiting between projects
                if self.rate_limit_delay > 0:
                    time.sleep(self.rate_limit_delay)

            # Compile report
            self._compile_report(overall_start_time)

            return self.report

        except Exception as e:
            logger.error(f"Fatal error: {e}")
            raise

    def _compile_report(self, start_time: float) -> None:
        """Compile final report."""
        self.report.total_time_seconds = time.time() - start_time
        self.report.total_api_calls = self.api_calls_made
        self.report.cache_hits = self.cache_hits
        self.report.branches_pruned = self.branches_pruned
        self.report.depth_reductions = self.depth_reductions
        self.report.timeout_retries = self.timeout_retries
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
        if self._component_depth_overrides:
            logger.info(f"  Components with Reduced Depth: {len(self._component_depth_overrides)}")

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

    def set_progress_callback(self, callback: Callable[[int, int], None]):
        self._progress_callback = callback

    def cancel_operation(self):
        self.cancel_event.set()


# Note: generate_excel_report is imported from validation_excel_report module


# =============================================================================
# MAIN
# =============================================================================

def main():
    """Run optimized validation."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )

    logger.info("=" * 60)
    logger.info("ARTIFACT STRUCTURE VALIDATOR - OPTIMIZED VERSION")
    logger.info("=" * 60)

    # Parse command line arguments (simple version)
    import sys

    concurrent = DEFAULT_CONCURRENT_REQUESTS
    children_level = DEFAULT_CHILDREN_LEVEL
    resume = False

    for arg in sys.argv[1:]:
        if arg.startswith('--concurrent='):
            concurrent = int(arg.split('=')[1])
        elif arg.startswith('--depth='):
            children_level = int(arg.split('=')[1])
        elif arg == '--resume':
            resume = True
        elif arg == '--help':
            logger.info("""
Usage: python artifact_structure_validator_optimized.py [OPTIONS]

Options:
    --concurrent=N    Max parallel API calls (default: 5)
    --depth=N         Children level to fetch (default: 3)
    --resume          Resume from last checkpoint
    --help            Show this help
            """)
            sys.exit(0)

    validator = OptimizedArtifactValidator(
        concurrent_requests=concurrent,
        children_level=children_level,
        enable_cache=True,
        enable_pruning=True,
        debug_mode=DEBUG_MODE
    )

    report = validator.run_validation(resume=resume)
    validator.print_summary()

    # Save reports
    output_dir = Path('.')
    validator.save_report(output_dir)

    # Generate Excel report with adaptive depth info
    generate_excel_report(
        report,
        output_dir,
        component_depth_overrides=validator._component_depth_overrides
    )

    logger.info("=" * 60)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
