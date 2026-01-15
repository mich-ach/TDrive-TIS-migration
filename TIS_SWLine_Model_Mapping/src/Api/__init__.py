"""TIS API HTTP Client with caching and retry logic.

This module handles all HTTP communication with the TIS API,
including connection pooling, caching, and retry mechanisms.

Classes:
    TISClient: HTTP client for TIS API with connection pooling, caching, and retry logic
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
)

logger = logging.getLogger(__name__)


class TISClient:
    """
    HTTP client for TIS API with connection pooling, caching, and retry logic.

    This class is responsible only for making HTTP requests to the TIS API.
    It handles:
    - Connection pooling for performance
    - Response caching to reduce API calls
    - Retry logic with exponential backoff
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
        concurrent_requests: int = 5
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
        """
        self.base_url = base_url
        self.timeout = timeout
        self.slow_mode = slow_mode
        self.wait_time = wait_time
        self.concurrent_requests = concurrent_requests

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

        # Statistics
        self.api_calls_made = 0
        self.cache_hits = 0

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
        if use_cache and url in self._cache:
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
            if use_cache and len(self._cache) < self._cache_max_size:
                self._cache[url] = data

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

    def get_component(
        self,
        component_id: str,
        children_level: int = 1,
        use_cache: bool = True,
        timeout: Optional[Tuple[float, float]] = None
    ) -> Tuple[Optional[Dict], bool, float]:
        """
        Fetch a component from TIS API.

        Args:
            component_id: The TIS component ID (rId)
            children_level: Depth of children to fetch (-1 for unlimited)
            use_cache: Whether to use cached responses
            timeout: Optional override for request timeout

        Returns:
            Tuple of (response_data, timed_out, elapsed_time)
        """
        url = f"{self.base_url}{component_id}?mappingType=TCI&childrenlevel={children_level}&attributes=true"
        logger.debug(f"API request (depth={children_level}): {url}")
        return self.get(url, use_cache=use_cache, timeout=timeout)

    def clear_cache(self) -> None:
        """Clear the response cache."""
        with self._lock:
            self._cache.clear()
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
                'cache_efficiency': cache_efficiency
            }

    def reset_statistics(self) -> None:
        """Reset client statistics."""
        with self._lock:
            self.api_calls_made = 0
            self.cache_hits = 0
