"""TIS API HTTP Client with caching, retry logic, and adaptive depth.

This module handles all HTTP communication with the TIS API,
including connection pooling, caching, adaptive depth, and retry mechanisms.

Classes:
    TISClient: HTTP client for TIS API with all optimizations
"""

import logging
import time
import threading
from typing import Dict, Optional, Tuple, Any

import requests
try:
    import ujson as json
except ImportError:
    import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import (
    TIS_URL,
    API_TIMEOUT,
    API_MAX_RETRIES,
    API_BACKOFF_FACTOR,
    API_RETRY_STATUS_CODES,
    CACHE_MAX_SIZE,
    SLOW_MODE,
    API_WAIT_TIME,
    ADAPTIVE_TIMEOUT_THRESHOLD,
    MIN_CHILDREN_LEVEL,
    DEPTH_REDUCTION_STEP,
    CONCURRENT_REQUESTS as DEFAULT_CONCURRENT_REQUESTS,
    CHILDREN_LEVEL as DEFAULT_CHILDREN_LEVEL,
)

logger = logging.getLogger(__name__)


class TISClient:
    """
    HTTP client for TIS API with connection pooling, caching, and adaptive depth.

    This class handles:
    - Connection pooling for performance
    - Response caching to reduce API calls
    - Retry logic with exponential backoff
    - Adaptive depth reduction on timeouts
    - Thread-safe operations
    """

    def __init__(
        self,
        base_url: str = TIS_URL,
        timeout: Tuple[float, float] = API_TIMEOUT,
        max_retries: int = API_MAX_RETRIES,
        backoff_factor: float = API_BACKOFF_FACTOR,
        retry_status_codes: list = None,
        cache_max_size: int = CACHE_MAX_SIZE,
        slow_mode: bool = SLOW_MODE,
        wait_time: int = API_WAIT_TIME,
        concurrent_requests: int = DEFAULT_CONCURRENT_REQUESTS,
        children_level: int = DEFAULT_CHILDREN_LEVEL,
        enable_cache: bool = True,
        debug_mode: bool = False
    ):
        """
        Initialize the TIS HTTP client.

        Args:
            base_url: Base URL for TIS API
            timeout: Tuple of (connect_timeout, read_timeout)
            max_retries: Maximum number of retry attempts
            backoff_factor: Exponential backoff multiplier
            retry_status_codes: HTTP status codes to retry on
            cache_max_size: Maximum number of cached responses
            slow_mode: If True, add delay between requests
            wait_time: Delay in seconds for slow mode
            concurrent_requests: Number of concurrent connections to maintain
            children_level: Default depth for fetching children
            enable_cache: Whether to enable response caching
            debug_mode: Enable debug logging
        """
        self.base_url = base_url
        self.timeout = timeout
        self.slow_mode = slow_mode
        self.wait_time = wait_time
        self.concurrent_requests = concurrent_requests
        self.children_level = children_level
        self.enable_cache = enable_cache
        self.debug_mode = debug_mode

        # Threading
        self._lock = threading.Lock()
        self._session_local = threading.local()

        # Retry configuration
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
        self._retry_status_codes = retry_status_codes or API_RETRY_STATUS_CODES

        # Cache
        self._cache: Dict[str, Dict] = {}
        self._cache_max_size = cache_max_size

        # Adaptive depth tracking - remember components that need lower depth
        self._component_depth_overrides: Dict[str, int] = {}

        # Statistics
        self.api_calls_made = 0
        self.cache_hits = 0
        self.depth_reductions = 0
        self.timeout_retries = 0

    def _get_session(self) -> requests.Session:
        """Get thread-local session with connection pooling."""
        if not hasattr(self._session_local, 'session'):
            session = requests.Session()
            retry_strategy = Retry(
                total=self._max_retries,
                read=0,  # Don't retry on read timeouts - let adaptive depth handle it
                backoff_factor=self._backoff_factor,
                status_forcelist=self._retry_status_codes,
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

    def get(
        self,
        url: str,
        use_cache: bool = True,
        timeout: Optional[Tuple[float, float]] = None
    ) -> Tuple[Optional[Dict], bool, float]:
        """
        Make a GET request to the TIS API.

        Args:
            url: Full URL to request
            use_cache: Whether to use cached responses
            timeout: Optional override for request timeout

        Returns:
            Tuple of (response_data, timed_out, elapsed_time)
        """
        # Check cache first
        if use_cache and self.enable_cache and url in self._cache:
            with self._lock:
                self.cache_hits += 1
            return self._cache[url], False, 0.0

        request_timeout = timeout or self.timeout
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
            data = json.loads(response.content)

            with self._lock:
                self.api_calls_made += 1

            # Cache response if enabled and cache not full
            if use_cache and self.enable_cache and len(self._cache) < self._cache_max_size:
                self._cache[url] = data

            if self.slow_mode:
                time.sleep(self.wait_time)

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

    def get_component(
        self,
        component_id: str,
        children_level: int = 1,
        use_cache: bool = True,
        timeout: Optional[Tuple[float, float]] = None
    ) -> Tuple[Optional[Dict], bool, float]:
        """
        Fetch a component from TIS API (simple, non-adaptive).

        Args:
            component_id: The TIS component ID (rId)
            children_level: Depth of children to fetch
            use_cache: Whether to use cached responses
            timeout: Optional override for request timeout

        Returns:
            Tuple of (response_data, timed_out, elapsed_time)
        """
        url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel={children_level}&attributes=true"
        if self.debug_mode:
            logger.debug(f"API request (depth={children_level}): {url}")
        return self.get(url, use_cache=use_cache, timeout=timeout)

    def get_component_adaptive(
        self,
        component_id: str,
        use_cache: bool = True
    ) -> Tuple[Optional[Dict], int]:
        """
        Fetch component with adaptive depth reduction on timeouts.

        If the request times out or takes too long, automatically reduces
        the children level and retries. Remembers components that need
        lower depth for future calls.

        Args:
            component_id: The TIS component ID (rId)
            use_cache: Whether to use cached responses

        Returns:
            Tuple of (response_data, depth_used)
        """
        # Check if we have a known depth override for this component
        current_depth = self._component_depth_overrides.get(component_id, self.children_level)

        while current_depth >= MIN_CHILDREN_LEVEL:
            url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel={current_depth}&attributes=true"

            # Use adaptive timeout based on depth
            adaptive_timeout = (5, ADAPTIVE_TIMEOUT_THRESHOLD + (current_depth * 2))

            data, timed_out, elapsed = self.get(url, use_cache=use_cache, timeout=adaptive_timeout)

            # Check if we got a response
            if data is not None:
                # If this was slower than threshold but succeeded, remember for future
                if elapsed > ADAPTIVE_TIMEOUT_THRESHOLD and current_depth > MIN_CHILDREN_LEVEL:
                    with self._lock:
                        # Store slightly lower depth for next time
                        self._component_depth_overrides[component_id] = max(
                            MIN_CHILDREN_LEVEL,
                            current_depth - DEPTH_REDUCTION_STEP
                        )
                    if self.debug_mode:
                        logger.debug(
                            f"Slow component {component_id}: {elapsed:.1f}s at depth {current_depth}, "
                            f"will use depth {self._component_depth_overrides[component_id]} next time"
                        )
                return data, current_depth

            # If timed out or no response, reduce depth and retry
            if timed_out or elapsed > ADAPTIVE_TIMEOUT_THRESHOLD:
                with self._lock:
                    self.timeout_retries += 1

                new_depth = current_depth - DEPTH_REDUCTION_STEP

                if new_depth >= MIN_CHILDREN_LEVEL:
                    with self._lock:
                        self.depth_reductions += 1
                    logger.warning(
                        f"Timeout: reducing depth {current_depth} -> {new_depth} for component {component_id}"
                    )

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

    def clear_cache(self) -> None:
        """Clear the response cache."""
        with self._lock:
            self._cache.clear()
            if self.debug_mode:
                logger.debug("Response cache cleared")

    def get_statistics(self) -> Dict[str, Any]:
        """Get client statistics."""
        with self._lock:
            total_requests = self.api_calls_made + self.cache_hits
            cache_efficiency = (self.cache_hits / total_requests * 100) if total_requests > 0 else 0.0
            return {
                'api_calls_made': self.api_calls_made,
                'cache_hits': self.cache_hits,
                'cache_size': len(self._cache),
                'cache_efficiency': cache_efficiency,
                'depth_reductions': self.depth_reductions,
                'timeout_retries': self.timeout_retries,
                'components_with_reduced_depth': len(self._component_depth_overrides)
            }

    def reset_statistics(self) -> None:
        """Reset client statistics."""
        with self._lock:
            self.api_calls_made = 0
            self.cache_hits = 0
            self.depth_reductions = 0
            self.timeout_retries = 0

    @property
    def component_depth_overrides(self) -> Dict[str, int]:
        """Get the component depth overrides dictionary."""
        return self._component_depth_overrides
