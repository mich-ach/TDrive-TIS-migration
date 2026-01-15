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
    RETRY_BACKOFF_SECONDS,
    FINAL_TIMEOUT_SECONDS,
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
        Fetch component with adaptive depth and retry logic.

        Strategy:
        1. If children_level is -1, use unlimited depth (no adaptive reduction)
        2. Otherwise, try at current depth with adaptive timeout
        3. If timeout, reduce depth and retry
        4. At minimum depth, retry with exponential backoff
        5. Final attempt with very long timeout

        Args:
            component_id: The TIS component ID (rId)
            use_cache: Whether to use cached responses

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
                url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel=-1&attributes=true"
                if self.debug_mode:
                    logger.debug(f"API request (unlimited depth): {url}")

                # Use short timeout for unlimited - fail fast if too slow
                unlimited_timeout = (10, 30)  # 30 second read timeout max

                data, timed_out, elapsed = self.get(url, timeout=unlimited_timeout)

                if data is not None:
                    if self.debug_mode:
                        logger.debug(f"Unlimited depth succeeded: {len(data.get('children', []))} children")
                    return data, -1

                # Unlimited failed - fall back to iterative exploration starting at depth 1
                logger.info(f"Unlimited depth timed out for {component_id}, switching to iterative exploration...")
                self._component_depth_overrides[component_id] = 1
                current_depth = 1

        # Phase 1: Try reducing depth (normal adaptive logic)
        while current_depth >= MIN_CHILDREN_LEVEL:
            url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel={current_depth}&attributes=true"
            if self.debug_mode:
                logger.debug(f"API request (depth={current_depth}): {url}")

            # Use adaptive timeout based on depth
            adaptive_timeout = (10, ADAPTIVE_TIMEOUT_THRESHOLD + (current_depth * 5))

            data, timed_out, elapsed = self.get(url, use_cache=use_cache, timeout=adaptive_timeout)

            if data is not None:
                if self.debug_mode:
                    logger.debug(f"API response: {len(data.get('children', []))} children")
                # If slow but succeeded, remember for future
                if elapsed > ADAPTIVE_TIMEOUT_THRESHOLD and current_depth > MIN_CHILDREN_LEVEL:
                    with self._lock:
                        self._component_depth_overrides[component_id] = max(
                            MIN_CHILDREN_LEVEL,
                            current_depth - DEPTH_REDUCTION_STEP
                        )
                    if self.debug_mode:
                        logger.debug(f"Slow response: {component_id} took {elapsed:.1f}s at depth {current_depth}")
                return data, current_depth

            # If timed out, reduce depth and retry
            if timed_out or elapsed > ADAPTIVE_TIMEOUT_THRESHOLD:
                with self._lock:
                    self.timeout_retries += 1

                new_depth = current_depth - DEPTH_REDUCTION_STEP

                if new_depth >= MIN_CHILDREN_LEVEL:
                    with self._lock:
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
        url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel={MIN_CHILDREN_LEVEL}&attributes=true"

        for retry_idx, backoff in enumerate(RETRY_BACKOFF_SECONDS):
            logger.info(f"Retry {retry_idx + 1}/{len(RETRY_BACKOFF_SECONDS)}: waiting {backoff}s for {component_id}")
            time.sleep(backoff)

            # Increase timeout with each retry
            retry_timeout = (10, 20 + (retry_idx * 10))
            data, timed_out, elapsed = self.get(url, timeout=retry_timeout, use_cache=False)

            if data is not None:
                logger.info(f"Recovered: {component_id} succeeded after {retry_idx + 1} retries ({elapsed:.1f}s)")
                self._component_depth_overrides[component_id] = MIN_CHILDREN_LEVEL
                return data, MIN_CHILDREN_LEVEL

            with self._lock:
                self.timeout_retries += 1

        # Phase 3: Final attempt with very long timeout
        logger.info(f"Final attempt: {component_id} with {FINAL_TIMEOUT_SECONDS}s timeout")
        final_timeout = (15, FINAL_TIMEOUT_SECONDS)
        data, timed_out, elapsed = self.get(url, timeout=final_timeout, use_cache=False)

        if data is not None:
            logger.info(f"Recovered: {component_id} succeeded on final attempt ({elapsed:.1f}s)")
            self._component_depth_overrides[component_id] = MIN_CHILDREN_LEVEL
            return data, MIN_CHILDREN_LEVEL

        # All attempts failed
        logger.warning(f"Skipped: {component_id} failed after all retries")
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
