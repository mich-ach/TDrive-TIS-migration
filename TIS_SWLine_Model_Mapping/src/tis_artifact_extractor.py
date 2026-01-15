"""
TIS Artifact Extractor - Optimized Recursive Version

This version uses recursive BFS search to find ALL vVeh artifacts regardless of their
location in the folder structure. Unlike the original extractor that only searched
expected paths (Project/SWLine/Model/HiL/CSP|SWB/), this version finds misplaced artifacts.

Features:
- Recursive BFS search (finds artifacts even in wrong paths)
- Adaptive depth reduction on API timeouts
- Concurrent API requests for performance
- Response caching to reduce API calls
- Smart branch pruning (skips unlikely folders)
- Same output format as original for workflow compatibility
"""

from typing import List, Dict, Any, Optional, Tuple, Set
import json
import time
import re
import threading
import logging
from pathlib import Path
import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import ujson
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from version_parser import VersionParser

# Import config properly
import config

from config import (
    # API settings
    TIS_URL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_BACKOFF_FACTOR,
    API_RETRY_STATUS_CODES,

    # Debug settings
    DEBUG_MODE,
    SLOW_MODE,
    API_WAIT_TIME,
    LOG_LEVEL,

    # File settings
    CURRENT_RUN_DIR,
    JSON_OUTPUT_PREFIX,
    LATEST_JSON_PREFIX,

    # TIS settings
    VW_XCU_PROJECT_ID,
    TIS_LINK_TEMPLATE,

    # Path convention settings
    PATH_VALID_SUBFOLDERS_HIL,
    LABCAR_PLATFORMS,

    # Artifact filter settings
    COMPONENT_TYPE_FILTER,
    COMPONENT_NAME_FILTER,
    COMPONENT_GRP_FILTER,
    LIFE_CYCLE_STATUS_FILTER,

    # Optimization settings (from config.py)
    CONCURRENT_REQUESTS,
    CHILDREN_LEVEL,
    UNLIMITED_FALLBACK_DEPTH,
    RATE_LIMIT_DELAY,
    CACHE_MAX_SIZE,
    ADAPTIVE_TIMEOUT_THRESHOLD,
    MIN_CHILDREN_LEVEL,
    DEPTH_REDUCTION_STEP,
    MAX_RETRIES_PER_COMPONENT,
    RETRY_BACKOFF_SECONDS,
    FINAL_TIMEOUT_SECONDS,
    SKIP_FOLDER_PATTERNS,

    # Workflow settings
    SKIP_DELETED_ARTIFACTS,

    # Display settings
    DATE_DISPLAY_FORMAT,

    # Branch pruning
    SKIP_PROJECTS,
    INCLUDE_PROJECTS,
    INCLUDE_SOFTWARE_LINES,
)

# =============================================================================
# LOGGING SETUP
# =============================================================================

# Create logger for this module
logger = logging.getLogger(__name__)

# Configure logging based on config
_log_level = getattr(logging, LOG_LEVEL, logging.INFO)
logging.basicConfig(
    level=_log_level,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger.setLevel(_log_level)


def _get_life_cycle_status(attributes: List[Dict]) -> Optional[str]:
    """Get the lifeCycleStatus value from attributes."""
    for attr in attributes:
        if attr.get('name') == 'lifeCycleStatus':
            return attr.get('value')
    return None


def _convert_ticks_to_iso(ticks_value: str) -> Optional[str]:
    """
    Convert .NET DateTime ticks to formatted date string.

    .NET DateTime ticks are 100-nanosecond intervals since January 1, 0001.
    TIS API returns dates in this format (e.g., "638349664128090000").

    The output format is configurable via DATE_DISPLAY_FORMAT in config.json.
    Default format: "%d-%m-%Y %H:%M:%S" (e.g., "03-10-2023 09:06:28")
    """
    if not ticks_value:
        return None

    try:
        # Check if it's already an ISO date string - convert to configured format
        if 'T' in str(ticks_value) or '-' in str(ticks_value):
            # Try to parse ISO format and reformat
            try:
                iso_str = str(ticks_value)
                if iso_str.endswith('Z'):
                    iso_str = iso_str[:-1]
                dt = datetime.datetime.fromisoformat(iso_str.split('.')[0])
                return dt.strftime(DATE_DISPLAY_FORMAT)
            except (ValueError, TypeError):
                return str(ticks_value)

        # Convert .NET ticks (100-nanosecond intervals since 0001-01-01)
        ticks = int(ticks_value)

        # .NET epoch is January 1, 0001
        # Unix epoch is January 1, 1970
        # Difference in seconds: 62135596800
        DOTNET_EPOCH_DIFF = 62135596800

        # Convert 100-nanosecond intervals to seconds
        unix_timestamp = (ticks / 10_000_000) - DOTNET_EPOCH_DIFF

        # Convert to datetime and format using configured display format
        dt = datetime.datetime.utcfromtimestamp(unix_timestamp)
        return dt.strftime(DATE_DISPLAY_FORMAT)
    except (ValueError, TypeError, OSError):
        return None


def _parse_ticks_to_datetime(ticks_value: str) -> Optional[datetime.datetime]:
    """
    Parse .NET DateTime ticks to a Python datetime object.

    Handles both ticks format (e.g., "638349664128090000") and ISO format.
    Returns None if parsing fails.
    """
    if not ticks_value:
        return None

    try:
        value_str = str(ticks_value)

        # Check if it's ISO format (contains 'T' or '-')
        if 'T' in value_str or '-' in value_str:
            iso_str = value_str
            if iso_str.endswith('Z'):
                iso_str = iso_str[:-1] + '+00:00'
            result = datetime.datetime.fromisoformat(iso_str.split('.')[0]).replace(
                tzinfo=datetime.timezone.utc
            )
            logger.debug(f"_parse_ticks_to_datetime: ISO format '{value_str}' -> {result}")
            return result

        # Parse .NET ticks (100-nanosecond intervals since 0001-01-01)
        ticks = int(value_str)
        DOTNET_EPOCH_DIFF = 62135596800  # seconds between 0001-01-01 and 1970-01-01
        unix_timestamp = (ticks / 10_000_000) - DOTNET_EPOCH_DIFF
        result = datetime.datetime.utcfromtimestamp(unix_timestamp).replace(
            tzinfo=datetime.timezone.utc
        )
        logger.debug(f"_parse_ticks_to_datetime: ticks '{value_str}' -> {result}")
        return result
    except (ValueError, TypeError, OSError) as e:
        logger.debug(f"_parse_ticks_to_datetime: failed to parse '{ticks_value}': {e}")
        return None


def _is_artifact_deleted(attributes: List[Dict]) -> bool:
    """
    Check if an artifact is deleted based on tisFileDeletedDate attribute.

    An artifact is considered deleted only if:
    1. It has a tisFileDeletedDate attribute with a non-null value
    2. The deletion date has already passed (is in the past)

    If the deletion date is in the future or cannot be parsed, the artifact
    is NOT considered deleted (safe default - don't exclude artifacts we're unsure about).
    """
    for attr in attributes:
        if attr.get('name') == 'tisFileDeletedDate':
            deleted_date_str = attr.get('value')
            logger.debug(f"_is_artifact_deleted: found tisFileDeletedDate, raw value={deleted_date_str!r}, type={type(deleted_date_str).__name__}")
            if deleted_date_str:
                deleted_date = _parse_ticks_to_datetime(deleted_date_str)
                logger.debug(f"_is_artifact_deleted: parsed to {deleted_date}")
                if deleted_date:
                    now = datetime.datetime.now(datetime.timezone.utc)
                    is_deleted = deleted_date <= now
                    logger.debug(f"_is_artifact_deleted: deleted_date={deleted_date}, now={now}, is_deleted={is_deleted}")
                    return is_deleted
                # If date parsing fails, assume NOT deleted (safe default)
                logger.debug(f"_is_artifact_deleted: parsing failed, returning False")
                return False
    return False


class TISAPIService:
    """
    Optimized TIS API Service with recursive artifact discovery.

    Unlike the original version that searched expected paths only,
    this version uses BFS to find all vVeh artifacts regardless of location.
    """

    def __init__(
        self,
        debug_mode: bool = DEBUG_MODE,
        slow_mode: bool = SLOW_MODE,
        wait_time: int = API_WAIT_TIME,
        concurrent_requests: int = CONCURRENT_REQUESTS,
        children_level: int = CHILDREN_LEVEL,
        enable_cache: bool = True,
        enable_pruning: bool = True
    ):
        self.debug_mode = debug_mode
        self.slow_mode = slow_mode
        self.wait_time = wait_time
        self.concurrent_requests = concurrent_requests
        self.children_level = children_level
        self.enable_cache = enable_cache
        self.enable_pruning = enable_pruning

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
        self.failed_components: List[str] = []  # Track components that failed all retries

        # Cache
        self._response_cache: Dict[str, Dict] = {}

        # Adaptive depth tracking
        self._component_depth_overrides: Dict[str, int] = {}

        # Thread-local session storage
        self._session_local = threading.local()

        # Compile skip patterns
        self._skip_patterns = [re.compile(p, re.IGNORECASE) for p in SKIP_FOLDER_PATTERNS]
        logger.debug(f"Loaded {len(self._skip_patterns)} skip patterns: {SKIP_FOLDER_PATTERNS}")

        if debug_mode:
            logger.info(f"Running in DEBUG mode")
            logger.debug(f"  Concurrent requests: {concurrent_requests}")
            logger.debug(f"  Children level: {children_level}")
            logger.debug(f"  Adaptive timeout: {ADAPTIVE_TIMEOUT_THRESHOLD}s")
            if slow_mode:
                logger.info(f"  SLOW mode enabled - waiting {wait_time} seconds between calls")

    def _get_session(self) -> requests.Session:
        """Get thread-local session with connection pooling."""
        if not hasattr(self._session_local, 'session'):
            session = requests.Session()
            retry_strategy = Retry(
                total=API_MAX_RETRIES,
                read=0,  # Don't retry on read timeouts - let adaptive depth logic handle it
                backoff_factor=API_BACKOFF_FACTOR,
                status_forcelist=API_RETRY_STATUS_CODES,
                allowed_methods=["GET"]
            )
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

            if self.slow_mode:
                time.sleep(self.wait_time)

            return data, False, elapsed

        except requests.exceptions.Timeout:
            elapsed = time.time() - start_time
            logger.warning(f"API request timed out after {elapsed:.1f}s: {url}")
            return None, True, elapsed

        except requests.exceptions.ReadTimeout:
            elapsed = time.time() - start_time
            logger.warning(f"API read timeout after {elapsed:.1f}s: {url}")
            return None, True, elapsed

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"API request failed after {elapsed:.1f}s: {url} - {e}")
            return None, False, elapsed

    def _should_skip_folder(self, folder_name: str) -> bool:
        """Determine if a folder should be skipped based on naming patterns."""
        if not self.enable_pruning:
            return False

        # Check skip patterns
        for pattern in self._skip_patterns:
            if pattern.match(folder_name):
                logger.debug(f"Pruned '{folder_name}' - matched pattern: {pattern.pattern}")
                return True

        return False

    def _fetch_component_adaptive(self, component_id: str) -> Tuple[Optional[Dict], int]:
        """
        Fetch component with adaptive depth and retry logic.

        Strategy:
        1. If children_level is -1, use unlimited depth (no adaptive reduction)
        2. Otherwise, try at current depth with adaptive timeout
        3. If timeout, reduce depth and retry
        4. At minimum depth, retry with exponential backoff
        5. Final attempt with very long timeout

        Returns:
            Tuple of (response_data, depth_used)
        """
        current_depth = self._component_depth_overrides.get(component_id, self.children_level)

        # Special case: -1 means try unlimited depth first, then fall back to iterative
        if current_depth == -1 or self.children_level == -1:
            # Check if we already have a fallback depth for this component
            if component_id in self._component_depth_overrides and self._component_depth_overrides[component_id] > 0:
                # Already fell back, use the stored depth and continue with normal logic
                current_depth = self._component_depth_overrides[component_id]
            else:
                # First try unlimited depth with short timeout (fail fast to iterative)
                url = f"{TIS_URL}{component_id}?mappingType=TCI&childrenlevel=-1&attributes=true"
                logger.debug(f"API request: {url}")

                # Use short timeout for unlimited - fail fast if too slow
                unlimited_timeout = (10, 30)  # 30 second read timeout max

                data, timed_out, elapsed = self._make_api_request(url, timeout=unlimited_timeout)

                if data is not None:
                    logger.debug(f"API response: {len(data.get('children', []))} children")
                    return data, -1

                # Unlimited failed - fall back to iterative exploration starting at depth 1
                logger.info(f"Unlimited depth timed out for {component_id}, switching to iterative exploration...")
                self._component_depth_overrides[component_id] = 1
                current_depth = 1

        # Phase 1: Try reducing depth (normal adaptive logic)
        while current_depth >= MIN_CHILDREN_LEVEL:
            url = f"{TIS_URL}{component_id}?mappingType=TCI&childrenlevel={current_depth}&attributes=true"
            logger.debug(f"API request (depth={current_depth}): {url}")

            # Use adaptive timeout based on depth
            adaptive_timeout = (10, ADAPTIVE_TIMEOUT_THRESHOLD + (current_depth * 5))

            data, timed_out, elapsed = self._make_api_request(url, timeout=adaptive_timeout)

            if data is not None:
                logger.debug(f"API response: {len(data.get('children', []))} children")
                # If slow but succeeded, remember for future
                if elapsed > ADAPTIVE_TIMEOUT_THRESHOLD and current_depth > MIN_CHILDREN_LEVEL:
                    with self.api_lock:
                        self._component_depth_overrides[component_id] = max(
                            MIN_CHILDREN_LEVEL,
                            current_depth - DEPTH_REDUCTION_STEP
                        )
                    logger.debug(f"Slow response: {component_id} took {elapsed:.1f}s at depth {current_depth}")
                return data, current_depth

            # If timed out, reduce depth and retry
            if timed_out or elapsed > ADAPTIVE_TIMEOUT_THRESHOLD:
                with self.api_lock:
                    self.timeout_retries += 1

                new_depth = current_depth - DEPTH_REDUCTION_STEP

                if new_depth >= MIN_CHILDREN_LEVEL:
                    with self.api_lock:
                        self.depth_reductions += 1
                    logger.warning(f"Timeout: reducing depth {current_depth} -> {new_depth} for {component_id}")

                    self._component_depth_overrides[component_id] = new_depth
                    current_depth = new_depth
                else:
                    # At minimum depth, move to Phase 2
                    break
            else:
                # Non-timeout error at this depth
                current_depth -= 1

        # Phase 2: Retry at minimum depth with exponential backoff
        url = f"{TIS_URL}{component_id}?mappingType=TCI&childrenlevel={MIN_CHILDREN_LEVEL}&attributes=true"

        for retry_idx, backoff in enumerate(RETRY_BACKOFF_SECONDS):
            logger.info(f"Retry {retry_idx + 1}/{len(RETRY_BACKOFF_SECONDS)}: waiting {backoff}s for {component_id}")
            time.sleep(backoff)

            # Increase timeout with each retry
            retry_timeout = (10, 20 + (retry_idx * 10))
            data, timed_out, elapsed = self._make_api_request(url, timeout=retry_timeout, use_cache=False)

            if data is not None:
                logger.info(f"Recovered: {component_id} succeeded after {retry_idx + 1} retries ({elapsed:.1f}s)")
                self._component_depth_overrides[component_id] = MIN_CHILDREN_LEVEL
                return data, MIN_CHILDREN_LEVEL

            with self.api_lock:
                self.timeout_retries += 1

        # Phase 3: Final attempt with very long timeout
        logger.info(f"Final attempt: {component_id} with {FINAL_TIMEOUT_SECONDS}s timeout")
        final_timeout = (15, FINAL_TIMEOUT_SECONDS)
        data, timed_out, elapsed = self._make_api_request(url, timeout=final_timeout, use_cache=False)

        if data is not None:
            logger.info(f"Recovered: {component_id} succeeded on final attempt ({elapsed:.1f}s)")
            self._component_depth_overrides[component_id] = MIN_CHILDREN_LEVEL
            return data, MIN_CHILDREN_LEVEL

        # All attempts failed - log and continue
        logger.warning(f"Skipped: {component_id} failed after all retries")
        with self.api_lock:
            self.failed_components.append(component_id)

        return None, MIN_CHILDREN_LEVEL

    def _extract_all_vveh_from_tree(
        self,
        data: Dict,
        current_path: List[str],
        results: List[Tuple[str, str, List[str], Dict]],
        _debug_stats: Dict = None
    ) -> None:
        """
        Recursively extract all vVeh components from a fetched tree.

        This is the key difference from the original - we find ALL vVeh components,
        not just those in the expected path structure.
        """
        # Initialize debug stats on first call
        if _debug_stats is None:
            _debug_stats = {
                'nodes_visited': 0,
                'nodes_with_attributes': 0,
                'artifact_containers': 0,
                'type_matches': 0,
                'component_matches': 0,
                'grp_matches': 0,
                'has_artifact_attr': 0,
                'status_matches': 0,
                'not_deleted': 0,
                'final_matches': 0,
                'sample_types': set(),
                'sample_components': set(),
                'sample_grps': set(),
            }

        _debug_stats['nodes_visited'] += 1

        component_id = data.get('rId')
        node_name = data.get('name', 'Unknown')
        full_path = current_path + [node_name]

        # Check if this component is an artifact candidate
        # Filters are optional - if set to null/None, that filter is disabled
        component_type_name = data.get('componentType', {}).get('name')  # e.g., "vVeh"
        component_def_name = data.get('component', {}).get('name')  # e.g., "vVeh_LCO"
        component_grp_name = data.get('componentGrp', {}).get('name')  # e.g., "TIS Artifact Container"
        attributes = data.get('attributes', [])

        # Collect samples of what we're seeing
        if component_type_name:
            _debug_stats['sample_types'].add(component_type_name)
        if component_def_name:
            _debug_stats['sample_components'].add(component_def_name)
        if component_grp_name:
            _debug_stats['sample_grps'].add(component_grp_name)

        if attributes:
            _debug_stats['nodes_with_attributes'] += 1

        if component_grp_name == "TIS Artifact Container":
            _debug_stats['artifact_containers'] += 1

        # Check each filter (None means filter is disabled)
        # COMPONENT_TYPE_FILTER and COMPONENT_NAME_FILTER can be lists of allowed values
        is_matching_type = COMPONENT_TYPE_FILTER is None or component_type_name in COMPONENT_TYPE_FILTER
        is_matching_component = COMPONENT_NAME_FILTER is None or component_def_name in COMPONENT_NAME_FILTER
        is_matching_grp = COMPONENT_GRP_FILTER is None or component_grp_name == COMPONENT_GRP_FILTER

        if is_matching_type:
            _debug_stats['type_matches'] += 1
        if is_matching_component:
            _debug_stats['component_matches'] += 1
        if is_matching_grp:
            _debug_stats['grp_matches'] += 1

        # Debug: Log when a component has attributes but doesn't match all filters
        if attributes and component_grp_name == "TIS Artifact Container":
            if not (is_matching_type and is_matching_component):
                logger.debug(f"Rejected artifact {component_id}: type={component_type_name}, component={component_def_name}")
            elif is_matching_type and is_matching_component and is_matching_grp:
                logger.debug(f"Accepted artifact {component_id}: type={component_type_name}, component={component_def_name}")

        if is_matching_type and is_matching_component and is_matching_grp and attributes:
            has_artifact = any(attr.get('name') == 'artifact' for attr in attributes)
            is_deleted = _is_artifact_deleted(attributes)
            life_cycle_status = _get_life_cycle_status(attributes)

            if has_artifact:
                _debug_stats['has_artifact_attr'] += 1

            # Check lifeCycleStatus filter (None or empty list disables the filter)
            is_matching_status = (
                not LIFE_CYCLE_STATUS_FILTER or
                life_cycle_status in LIFE_CYCLE_STATUS_FILTER
            )

            if is_matching_status:
                _debug_stats['status_matches'] += 1
            if not is_deleted:
                _debug_stats['not_deleted'] += 1

            # Include artifact if all conditions are met
            if (has_artifact and
                (not SKIP_DELETED_ARTIFACTS or not is_deleted) and
                is_matching_status):
                _debug_stats['final_matches'] += 1
                results.append((component_id, node_name, full_path, data))

        # Process children
        children = data.get('children', [])
        if len(current_path) == 1:  # Only log for root level
            logger.debug(f"Root node '{node_name}' has {len(children)} children")

        for child in children:
            child_name = child.get('name', 'Unknown')

            # Apply branch pruning
            if self._should_skip_folder(child_name):
                with self.api_lock:
                    self.branches_pruned += 1
                continue

            if len(current_path) <= 2:
                logger.debug(f"Processing child '{child_name}'")
            self._extract_all_vveh_from_tree(child, full_path, results, _debug_stats)

        # Log debug summary at root level (when we return to original caller)
        if len(current_path) == 1 and _debug_stats['nodes_visited'] > 0:
            logger.debug(
                f"Tree stats: visited={_debug_stats['nodes_visited']}, "
                f"containers={_debug_stats['artifact_containers']}, "
                f"matches={_debug_stats['final_matches']}"
            )
            if _debug_stats['final_matches'] == 0 and _debug_stats['artifact_containers'] > 0:
                logger.debug(
                    f"No matches found. Sample types: {list(_debug_stats['sample_types'])[:5]}, "
                    f"Sample components: {list(_debug_stats['sample_components'])[:5]}"
                )

    def _find_unexplored_leaves(
        self,
        data: Dict,
        current_path: List[str],
        fetch_depth: int = None
    ) -> List[Tuple[str, List[str]]]:
        """Find leaf nodes that might have unexplored children.

        Args:
            data: The tree data to search
            current_path: Current path in the tree
            fetch_depth: The actual depth used when fetching (defaults to self.children_level)
        """
        leaves = []
        # Use the actual fetch depth, not the configured children_level
        effective_depth = fetch_depth if fetch_depth is not None else self.children_level

        # If unlimited depth was used successfully, no leaves to explore
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
        """Explore a leaf node for more artifacts using adaptive depth.

        Returns:
            Tuple of (results, data, depth_used) for further exploration
        """
        results = []

        data, depth_used = self._fetch_component_adaptive(node_id)
        if not data:
            return results, None, depth_used

        self._extract_all_vveh_from_tree(data, current_path[:-1], results)
        return results, data, depth_used

    def _process_software_line_recursive(
        self,
        sw_line_id: str,
        sw_line_name: str,
        project_name: str
    ) -> List[Dict[str, Any]]:
        """
        Process a software line using recursive BFS to find ALL artifacts.

        Returns artifacts in the format expected by the original workflow.
        """
        artifacts = []
        version_parser = VersionParser()

        # Fetch with adaptive children level
        data, depth_used = self._fetch_component_adaptive(sw_line_id)
        if not data:
            return artifacts

        # DEBUG: Show what we got from API
        children_count = len(data.get('children', []))
        logger.debug(f"Fetched '{sw_line_name}' (id={sw_line_id}) at depth={depth_used}, {children_count} children")
        if children_count == 0:
            logger.warning(f"No children returned for {sw_line_name}. Response keys: {list(data.keys())}")

        # Extract all vVeh candidates from the tree
        candidates: List[Tuple[str, str, List[str], Dict]] = []
        self._extract_all_vveh_from_tree(data, [project_name], candidates)

        # If tree wasn't deep enough, continue searching iteratively
        # Pass the actual depth used so leaf detection works correctly
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

                        # Find more leaves from this node if it was fetched at limited depth
                        if leaf_data and leaf_depth != -1:
                            leaf_id, leaf_path = futures[future]
                            more_leaves = self._find_unexplored_leaves(leaf_data, leaf_path, leaf_depth)
                            new_leaves.extend(more_leaves)

                        # Log progress every 10 nodes or at the end
                        if processed % 10 == 0 or processed == total_leaves:
                            logger.info(f"    Progress: {processed}/{total_leaves} nodes, {len(candidates)} artifacts found")
                    except Exception as e:
                        logger.error(f"Error processing leaf: {e}")

                if RATE_LIMIT_DELAY > 0:
                    time.sleep(RATE_LIMIT_DELAY)

            # Continue with newly discovered leaves
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

    def _extract_artifact_info(
        self,
        component_data: Dict,
        component_path: str,
        component_id: str,
        version_parser: VersionParser
    ) -> Optional[Dict[str, Any]]:
        """
        Extract artifact information in the format expected by the workflow.

        This maintains compatibility with excel_handler.py.
        """
        attributes = component_data.get('attributes', [])

        # Get actual component type info from API (for debugging/verification)
        actual_component_type = component_data.get('componentType', {}).get('name', 'Unknown')
        actual_component_name = component_data.get('component', {}).get('name', 'Unknown')
        actual_component_grp = component_data.get('componentGrp', {}).get('name', 'Unknown')

        # Build condensed attributes
        condensed = {
            'component_type': actual_component_name,  # Use actual API value, not hardcoded
            'component_type_category': actual_component_type,  # Store the componentType.name
            'component_grp': actual_component_grp,  # Store the componentGrp.name
            'simulation_type': 'HiL',
            'software_type': self._extract_software_type(component_path),
            'labcar_type': self._extract_labcar_type(component_path),
            'user': None,
            'lco_version': None,
            'vemox_version': None,
            'is_genuine_build': None,
            'life_cycle_status': None,
            'release_date_time': None,
            'created_date': None,
            'is_deleted': False,
            'deleted_date': None,
            'build_type': None
        }

        # Extract created date from top-level component data (not attributes)
        created_ticks = component_data.get('created')
        if created_ticks:
            condensed['created_date'] = _convert_ticks_to_iso(created_ticks)
            logger.debug(f"Extracted created_date: {created_ticks} -> {condensed['created_date']}")
        else:
            logger.debug(f"No 'created' field in component_data. Keys: {list(component_data.keys())}")

        for attr in attributes:
            name = attr.get('name')
            value = attr.get('value')

            if not name or value is None:
                continue

            if name == 'user':
                condensed['user'] = value.lower() if value else value
            elif name == 'isGenuineBuild':
                condensed['is_genuine_build'] = str(value).lower() == 'true'
            elif name == 'lifeCycleStatus':
                condensed['life_cycle_status'] = value
            elif name == 'releaseDateTime':
                condensed['release_date_time'] = _convert_ticks_to_iso(value)
            elif name == 'tisFileDeletedDate':
                condensed['deleted_date'] = _convert_ticks_to_iso(value)
                # is_deleted is set based on whether deletion date has passed
                is_deleted_result = _is_artifact_deleted(attributes)
                condensed['is_deleted'] = is_deleted_result
                logger.debug(f"tisFileDeletedDate: raw={value}, converted={condensed['deleted_date']}, is_deleted={is_deleted_result}")
            elif name == 'lcType':
                if not condensed['labcar_type']:
                    condensed['labcar_type'] = value
            elif name == 'execution' and value:
                condensed['lco_version'] = self._extract_lco_version(value)
            elif name == 'sources' and value:
                condensed['vemox_version'] = self._extract_vemox_version(value, version_parser)

        # Create artifact info in original format
        return {
            'name': component_data.get('name', 'Unknown'),
            'artifact_rid': component_id,
            'component_type': condensed['component_type'],
            'component_type_category': condensed['component_type_category'],
            'component_grp': condensed['component_grp'],
            'simulation_type': condensed['simulation_type'],
            'software_type': condensed['software_type'],
            'labcar_type': condensed['labcar_type'],
            'user': condensed['user'],
            'lco_version': condensed['lco_version'],
            'vemox_version': condensed['vemox_version'],
            'is_genuine_build': condensed['is_genuine_build'],
            'life_cycle_status': condensed['life_cycle_status'],
            'release_date_time': condensed['release_date_time'],
            'created_date': condensed['created_date'],
            'is_deleted': condensed['is_deleted'],
            'deleted_date': condensed['deleted_date'],
            'build_type': condensed['build_type'],
            'upload_path': component_path
        }

    def _extract_software_type(self, path: str) -> Optional[str]:
        """Extract software type (CSP/SWB) from path."""
        path_parts = path.split('/')
        for part in path_parts:
            for subfolder in PATH_VALID_SUBFOLDERS_HIL:
                if subfolder in part:
                    return part
        return None

    def _extract_labcar_type(self, path: str) -> Optional[str]:
        """Extract labcar type (VME/PCIe) from path."""
        path_parts = path.split('/')
        for part in path_parts:
            if part in LABCAR_PLATFORMS:
                return part
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

    def print_statistics(self) -> None:
        """Log optimization statistics."""
        logger.info("=== Extraction Statistics ===")
        logger.info(f"API Calls: {self.api_calls_made}, Cache Hits: {self.cache_hits}, Branches Pruned: {self.branches_pruned}")
        logger.info(f"Timeout Retries: {self.timeout_retries}, Depth Reductions: {self.depth_reductions}, Failed: {len(self.failed_components)}")
        if self.api_calls_made > 0:
            efficiency = self.cache_hits / (self.api_calls_made + self.cache_hits) * 100
            logger.info(f"Cache Efficiency: {efficiency:.1f}%")
        if self.failed_components:
            logger.warning(f"Components that failed all retries: {self.failed_components[:10]}")


def find_vveh_lco_components(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Legacy function for backward compatibility.
    Now uses recursive search instead of name-based search.
    """
    results = []

    def recursive_search(item: Dict, path: List[str]):
        # Check for artifact component - filters are optional (None disables the filter)
        component_type_name = item.get('componentType', {}).get('name')  # e.g., "vVeh"
        component_def_name = item.get('component', {}).get('name')  # e.g., "vVeh_LCO"
        component_grp_name = item.get('componentGrp', {}).get('name')  # e.g., "TIS Artifact Container"
        attributes = item.get('attributes', [])

        is_matching_type = COMPONENT_TYPE_FILTER is None or component_type_name == COMPONENT_TYPE_FILTER
        is_matching_component = COMPONENT_NAME_FILTER is None or component_def_name == COMPONENT_NAME_FILTER
        is_matching_grp = COMPONENT_GRP_FILTER is None or component_grp_name == COMPONENT_GRP_FILTER

        if is_matching_type and is_matching_component and is_matching_grp:
            has_artifact = any(attr.get('name') == 'artifact' for attr in attributes)
            is_deleted = _is_artifact_deleted(attributes)
            life_cycle_status = _get_life_cycle_status(attributes)

            # Check lifeCycleStatus filter (None or empty list disables the filter)
            is_matching_status = (
                not LIFE_CYCLE_STATUS_FILTER or
                life_cycle_status in LIFE_CYCLE_STATUS_FILTER
            )

            # Include artifact if all conditions are met
            if (has_artifact and
                (not SKIP_DELETED_ARTIFACTS or not is_deleted) and
                is_matching_status):
                results.append({
                    'rId': item.get('rId'),
                    'name': item.get('name'),
                    'path': '/'.join(path),
                    'attributes': attributes
                })

        for child in item.get('children', []):
            recursive_search(child, path + [child.get('name', '')])

    recursive_search(data, [data.get('name', '')])
    return results


def print_summary(structured_data: Dict) -> None:
    """Log summary of matches."""
    total_artifacts = 0
    for project_name, project_data in structured_data.items():
        for software_line_name, software_line_data in project_data['software_lines'].items():
            artifacts = software_line_data['artifacts']
            total_artifacts += len(artifacts)
            if artifacts:
                logger.info(f"Project {project_name}/{software_line_name}: {len(artifacts)} artifacts")

    logger.info(f"Total artifacts found: {total_artifacts}")


def print_latest_summary(latest_artifacts: Dict[str, Any]) -> None:
    """Log a summary of the latest artifacts."""
    logger.info("Summary of Latest Artifacts:")
    count = 0
    for project_name, project_data in latest_artifacts.items():
        for sw_line_name, sw_line_data in project_data['software_lines'].items():
            if sw_line_data['latest_artifact'] is not None:
                latest = sw_line_data['latest_artifact']
                count += 1
                logger.debug(f"Latest artifact: {project_name}/{sw_line_name} -> {latest['name']}")
    logger.info(f"Total software lines with artifacts: {count}")


def save_results(structured_data: Dict) -> None:
    """Save the structured data to a JSON file with timestamp."""
    if not config.CURRENT_RUN_DIR:
        raise ValueError("Run directory not configured!")

    output_file = config.CURRENT_RUN_DIR / f"{JSON_OUTPUT_PREFIX}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    try:
        logger.info(f"Saving results to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(structured_data, f, indent=2, default=str)
        logger.info("Results successfully saved")
    except Exception as e:
        raise ValueError(f"Error saving results to file: {e}")


def save_latest_artifacts(latest_artifacts: Dict[str, Any]) -> None:
    """Save the latest artifacts data to a JSON file."""
    if not config.CURRENT_RUN_DIR:
        raise ValueError("Run directory not configured!")

    output_file = config.CURRENT_RUN_DIR / f"{LATEST_JSON_PREFIX}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

    try:
        logger.info(f"Saving latest artifacts to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(latest_artifacts, f, indent=2, default=str)
        logger.info("Latest artifacts successfully saved")
    except Exception as e:
        raise ValueError(f"Error saving latest artifacts to file: {e}")


def extract_latest_artifacts(input_file: str) -> Dict[str, Any]:
    """
    Extract the latest artifact (highest rId) for each software line.
    Include empty software lines.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    latest_artifacts = {}

    for project_name, project_data in data.items():
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


def sort_structured_data(structured_data: Dict) -> Dict:
    """Sort the structured data by rail_rid and artifact_rid in descending order."""
    for project_name, project_data in structured_data.items():
        sorted_software_lines = dict(sorted(
            project_data['software_lines'].items(),
            key=lambda x: int(x[1]['software_line_rid']),
            reverse=True
        ))

        for software_line in sorted_software_lines.values():
            software_line['artifacts'] = sorted(
                software_line['artifacts'],
                key=lambda x: int(x['artifact_rid']),
                reverse=True
            )

        structured_data[project_name]['software_lines'] = sorted_software_lines

    return structured_data


def main() -> bool:
    """
    Main function to extract artifacts from TIS using recursive search.

    This version finds ALL vVeh artifacts regardless of their folder location,
    unlike the original which only searched expected paths.
    """
    try:
        # Validate run directory at the start
        if not config.CURRENT_RUN_DIR or not isinstance(config.CURRENT_RUN_DIR, Path):
            raise ValueError("Run directory not properly configured!")

        structured_data = {}

        logger.info("=" * 60)
        logger.info("TIS ARTIFACT EXTRACTOR - OPTIMIZED RECURSIVE VERSION")
        logger.info("=" * 60)

        tis_service = TISAPIService(
            debug_mode=DEBUG_MODE,
            slow_mode=SLOW_MODE,
            wait_time=API_WAIT_TIME,
            concurrent_requests=CONCURRENT_REQUESTS,
            children_level=CHILDREN_LEVEL,
            enable_cache=True,
            enable_pruning=True
        )

        # Get all projects
        projects_url = f"{TIS_URL}{VW_XCU_PROJECT_ID}?mappingType=TCI&childrenlevel=1"
        projects_response, _, _ = tis_service._make_api_request(projects_url)

        if not projects_response:
            logger.error("Failed to get projects response")
            return False

        projects = projects_response.get('children', [])
        total_projects = len(projects)
        logger.info(f"Found {total_projects} projects to process")

        # In debug mode, only process the first project
        if DEBUG_MODE:
            projects = projects[:1]
            logger.info("DEBUG MODE: Processing only the first project")

        for project_idx, project in enumerate(projects, 1):
            if tis_service.cancel_event.is_set():
                logger.warning("Cancelled")
                break

            project_id = project.get('rId')
            project_name = project.get('name')

            # Skip projects in the skip_projects list
            if project_name in SKIP_PROJECTS:
                logger.debug(f"[{project_idx}/{total_projects}] Skipping project: {project_name} (in skip_projects)")
                continue

            # Filter by include_projects (empty list = include all)
            if INCLUDE_PROJECTS and project_name not in INCLUDE_PROJECTS:
                logger.debug(f"[{project_idx}/{total_projects}] Skipping project: {project_name} (not in include_projects)")
                continue

            logger.info(f"[{project_idx}/{total_projects}] Processing project: {project_name}")

            project_url = f"{TIS_URL}{project_id}?mappingType=TCI&childrenlevel=1"
            project_response, _, _ = tis_service._make_api_request(project_url)

            if not project_response:
                continue

            software_lines = project_response.get('children', [])
            logger.info(f"  Found {len(software_lines)} software lines")

            # Initialize project in structured data
            structured_data[project_name] = {
                'project_rid': project_id,
                'software_lines': {}
            }

            # Process software lines concurrently
            total_sw_lines = len(software_lines)
            processed_count = 0
            total_artifacts_in_project = 0

            with ThreadPoolExecutor(max_workers=tis_service.concurrent_requests) as executor:
                futures = {}
                for sw_line in software_lines:
                    sw_line_id = sw_line.get('rId')
                    sw_line_name = sw_line.get('name')

                    # Filter by include_software_lines (empty list = include all)
                    if INCLUDE_SOFTWARE_LINES and sw_line_name not in INCLUDE_SOFTWARE_LINES:
                        continue

                    # Initialize software line
                    structured_data[project_name]['software_lines'][sw_line_name] = {
                        'software_line_rid': sw_line_id,
                        'artifacts': []
                    }

                    if sw_line_id:
                        future = executor.submit(
                            tis_service._process_software_line_recursive,
                            sw_line_id,
                            sw_line_name,
                            project_name
                        )
                        futures[future] = sw_line_name

                for future in as_completed(futures):
                    if tis_service.cancel_event.is_set():
                        break
                    try:
                        sw_artifacts = future.result()
                        sw_name = futures[future]
                        processed_count += 1
                        with tis_service.results_lock:
                            structured_data[project_name]['software_lines'][sw_name]['artifacts'] = sw_artifacts
                            artifact_count = len(sw_artifacts) if sw_artifacts else 0
                            total_artifacts_in_project += artifact_count
                            # Show progress for each software line
                            logger.info(f"    [{processed_count}/{total_sw_lines}] {sw_name}: {artifact_count} artifacts")
                    except Exception as e:
                        processed_count += 1
                        logger.error(f"    [{processed_count}/{total_sw_lines}] Error processing: {e}")

            # Summary for this project
            logger.info(f"  -> Project complete: {total_artifacts_in_project} total artifacts found")

            # Rate limiting between projects
            if RATE_LIMIT_DELAY > 0:
                time.sleep(RATE_LIMIT_DELAY)

        # Print statistics
        tis_service.print_statistics()

        print_summary(structured_data)
        save_results(structured_data)

        # Find the most recent artifacts file
        artifact_files = list(config.CURRENT_RUN_DIR.glob(f'{JSON_OUTPUT_PREFIX}_*.json'))

        if not artifact_files:
            logger.error("No artifact files found!")
            return False

        # Get the most recent file
        latest_file = max(artifact_files, key=lambda x: x.stat().st_mtime)
        logger.info(f"Processing file: {latest_file}")

        # Extract and process the latest artifacts
        latest_artifacts = extract_latest_artifacts(str(latest_file))

        # Print summary
        print_latest_summary(latest_artifacts)

        # Save latest artifacts
        save_latest_artifacts(latest_artifacts)

        logger.info("=" * 60)
        logger.info("EXTRACTION COMPLETE")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"Error in TIS artifact extraction: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    main()
