"""
Image Validator - Validates image URLs and extracts dimensions.
"""
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

try:
    from PIL import Image
    from io import BytesIO
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ImageValidationResult:
    """Result of image validation."""
    url: str
    accessible: bool = False
    content_type: Optional[str] = None
    content_length: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    error: Optional[str] = None
    final_url: Optional[str] = None


class ImageValidator:
    """
    Validates image URLs and optionally extracts dimensions.
    
    Uses HTTP HEAD for quick validation, falls back to partial GET
    for dimension extraction when PIL is available.
    """

    # Cache for validation results (in-memory, TTL-based)
    _cache: Dict[str, ImageValidationResult] = {}
    _cache_timestamps: Dict[str, float] = {}
    CACHE_TTL = 300  # 5 minutes

    # Recommended OG image dimensions
    RECOMMENDED_WIDTH = 1200
    RECOMMENDED_HEIGHT = 630
    MIN_WIDTH = 200
    MIN_HEIGHT = 200
    MAX_FILE_SIZE = 8 * 1024 * 1024  # 8MB

    def __init__(
        self,
        timeout: float = 5.0,
        max_redirects: int = 5,
        user_agent: Optional[str] = None,
        enable_dimension_check: bool = True,
    ):
        self.timeout = timeout
        self.max_redirects = max_redirects
        self.user_agent = user_agent or "Mozilla/5.0 (compatible; SEOBot/1.0; +https://example.com/bot)"
        self.enable_dimension_check = enable_dimension_check and PIL_AVAILABLE
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                max_redirects=self.max_redirects,
                headers={"User-Agent": self.user_agent},
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def __aenter__(self) -> "ImageValidator":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def _get_cache_key(self, url: str) -> str:
        """Generate cache key from URL."""
        return url.strip().lower()

    def _is_cached(self, url: str) -> bool:
        """Check if URL is in cache and not expired."""
        import time
        key = self._get_cache_key(url)
        if key not in self._cache:
            return False
        if time.time() - self._cache_timestamps.get(key, 0) > self.CACHE_TTL:
            # Expired, remove
            self._cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
            return False
        return True

    def _get_cached(self, url: str) -> Optional[ImageValidationResult]:
        """Get cached result."""
        key = self._get_cache_key(url)
        return self._cache.get(key)

    def _set_cache(self, url: str, result: ImageValidationResult) -> None:
        """Store result in cache."""
        import time
        key = self._get_cache_key(url)
        self._cache[key] = result
        self._cache_timestamps[key] = time.time()

    async def validate(self, url: str) -> ImageValidationResult:
        """
        Validate an image URL.
        
        Args:
            url: Image URL to validate
            
        Returns:
            ImageValidationResult with validation details
        """
        if not url:
            return ImageValidationResult(url=url, accessible=False, error="Empty URL")

        # Check cache
        if self._is_cached(url):
            cached = self._get_cached(url)
            if cached:
                logger.debug(f"Cache hit for image validation: {url}")
                return cached

        result = await self._validate_impl(url)
        self._set_cache(url, result)
        return result

    async def _validate_impl(self, url: str) -> ImageValidationResult:
        """Internal validation implementation."""
        client = await self._get_client()
        result = ImageValidationResult(url=url)

        try:
            # First try HEAD request for quick validation
            head_response = await client.head(url)
            result.final_url = str(head_response.url)
            result.accessible = 200 <= head_response.status_code < 400
            result.content_type = head_response.headers.get("content-type")
            
            content_length = head_response.headers.get("content-length")
            if content_length:
                try:
                    result.content_length = int(content_length)
                except ValueError:
                    pass

            if not result.accessible:
                result.error = f"HTTP {head_response.status_code}"
                return result

            # Check if it's an image
            if result.content_type and not result.content_type.startswith("image/"):
                result.error = f"Not an image: {result.content_type}"
                result.accessible = False
                return result

            # Check file size
            if result.content_length and result.content_length > self.MAX_FILE_SIZE:
                result.error = f"File too large: {result.content_length} bytes"
                # Don't mark as inaccessible, just warn

            # Try to get dimensions if enabled
            if self.enable_dimension_check:
                await self._extract_dimensions(client, result)

        except httpx.TimeoutException:
            result.error = "Timeout"
            result.accessible = False
        except httpx.TooManyRedirects:
            result.error = "Too many redirects"
            result.accessible = False
        except httpx.RequestError as e:
            result.error = f"Request error: {type(e).__name__}"
            result.accessible = False
        except Exception as e:
            logger.warning(f"Unexpected error validating image {url}: {e}")
            result.error = f"Validation error: {type(e).__name__}"
            result.accessible = False

        return result

    async def _extract_dimensions(self, client: httpx.AsyncClient, result: ImageValidationResult) -> None:
        """Extract image dimensions by downloading a portion of the image."""
        if not PIL_AVAILABLE:
            return

        url = result.final_url or result.url
        try:
            # Use GET with Range header to fetch only first 32KB
            # This is usually enough for image headers
            headers = {"Range": "bytes=0-32767"}
            response = await client.get(url, headers=headers)
            
            if response.status_code not in (200, 206):
                # Fallback: try full GET if Range not supported
                response = await client.get(url)
                if response.status_code != 200:
                    return

            content = response.content
            if not content:
                return

            # Parse with PIL
            try:
                img = Image.open(BytesIO(content))
                result.width = img.width
                result.height = img.height
                img.close()
            except Exception as e:
                logger.debug(f"Failed to parse image dimensions for {url}: {e}")

        except Exception as e:
            logger.debug(f"Failed to fetch image for dimensions {url}: {e}")

    async def validate_multiple(self, urls: list[str]) -> Dict[str, ImageValidationResult]:
        """Validate multiple URLs concurrently."""
        tasks = [self.validate(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        validated = {}
        for url, result in zip(urls, results):
            if isinstance(result, Exception):
                validated[url] = ImageValidationResult(
                    url=url, accessible=False, error=f"Validation failed: {result}"
                )
            else:
                validated[url] = result
        return validated

    def check_dimensions(self, result: ImageValidationResult) -> Dict[str, any]:
        """
        Check if image dimensions meet recommendations.
        
        Returns dict with:
        - meets_recommended: bool
        - meets_minimum: bool
        - issues: list of str
        - aspect_ratio: float or None
        """
        issues = []
        meets_recommended = False
        meets_minimum = False
        aspect_ratio = None

        if result.width and result.height:
            aspect_ratio = round(result.width / result.height, 2)
            
            # Check minimum
            if result.width >= self.MIN_WIDTH and result.height >= self.MIN_HEIGHT:
                meets_minimum = True
            else:
                issues.append(f"Below minimum dimensions ({self.MIN_WIDTH}x{self.MIN_HEIGHT}): {result.width}x{result.height}")

            # Check recommended
            if result.width >= self.RECOMMENDED_WIDTH and result.height >= self.RECOMMENDED_HEIGHT:
                meets_recommended = True
            else:
                issues.append(f"Below recommended dimensions ({self.RECOMMENDED_WIDTH}x{self.RECOMMENDED_HEIGHT}): {result.width}x{result.height}")

            # Check aspect ratio (1.91:1 is ideal for OG)
            ideal_ratio = 1.91
            if aspect_ratio:
                ratio_diff = abs(aspect_ratio - ideal_ratio) / ideal_ratio
                if ratio_diff > 0.1:  # More than 10% off
                    issues.append(f"Aspect ratio {aspect_ratio:.2f} differs from ideal 1.91:1")
        else:
            issues.append("Dimensions unknown (could not fetch/parse image)")

        return {
            "meets_recommended": meets_recommended,
            "meets_minimum": meets_minimum,
            "issues": issues,
            "aspect_ratio": aspect_ratio,
            "width": result.width,
            "height": result.height,
        }


# Global instance for easy access
_global_validator: Optional[ImageValidator] = None


def get_image_validator(**kwargs) -> ImageValidator:
    """Get or create global image validator instance."""
    global _global_validator
    if _global_validator is None:
        _global_validator = ImageValidator(**kwargs)
    return _global_validator


async def close_image_validator() -> None:
    """Close global image validator."""
    global _global_validator
    if _global_validator:
        await _global_validator.close()
        _global_validator = None