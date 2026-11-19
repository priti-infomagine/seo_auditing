from __future__ import annotations

import re
from urllib.parse import urlparse

_GENERIC_ALT_PATTERNS = frozenset({
    "image", "photo", "picture", "banner", "hero", "logo",
    "click here", "here", "read more", "learn more", "more",
    "default", "untitled", "stock", "placeholder", "lorem", "ipsum",
    "image of", "picture of", "photo of",
})

_GENERIC_FILENAME_RE = re.compile(
    r'^(IMG_|DSC_|DSCF_|PANO_|PHT_|screenshot|screen_shot|screen-'
    r'|image[\d_]*\.|photo[\d_]*\.|untitled[\d_]*\.|blob[\d_]*\.|'
    r'[a-f0-9]{8,}\.[a-z]+)$',
    re.IGNORECASE,
)

_MODERN_FORMATS = frozenset({"webp", "avif", "jpeg2000", "jxl", "heic", "heif"})


def _get_filename(url: str) -> str:
    """Extract filename from URL."""
    try:
        parsed = urlparse(url)
        return parsed.path.split("/")[-1]
    except Exception:
        return ""


def _is_modern_format(url: str) -> bool:
    """Check if URL uses a modern image format."""
    ext = urlparse(url).path.lower().split(".")[-1] if url else ""
    return ext in _MODERN_FORMATS


def _is_generic_alt(alt: str) -> bool:
    """Check if alt text is generic/non-descriptive."""
    alt_lower = alt.lower().strip()
    if alt_lower in _GENERIC_ALT_PATTERNS:
        return True
    for pattern in _GENERIC_ALT_PATTERNS:
        if pattern in alt_lower:
            return True
    return False


def _is_generic_filename(filename: str) -> bool:
    """Check if filename is generic/non-descriptive."""
    if not filename:
        return False
    return bool(_GENERIC_FILENAME_RE.match(filename))


def _has_dimensions(img) -> bool:
    """Check if image has both width and height attributes."""
    width = getattr(img, "width", "") or (img.get("width", "") if isinstance(img, dict) else "")
    height = getattr(img, "height", "") or (img.get("height", "") if isinstance(img, dict) else "")
    return bool(width and height)


def _has_srcset(img) -> bool:
    srcset = getattr(img, "srcset", "") or (img.get("srcset", "") if isinstance(img, dict) else "")
    return bool(srcset)


def _has_sizes(img) -> bool:
    sizes = getattr(img, "sizes", "") or (img.get("sizes", "") if isinstance(img, dict) else "")
    return bool(sizes)


def _has_lazy_loading(img) -> bool:
    loading = getattr(img, "loading", "") or (img.get("loading", "") if isinstance(img, dict) else "")
    return loading.strip().lower() == "lazy"


def _is_broken_image(img) -> bool:
    """Check if image is broken (HTTP error, empty src, placeholder)."""
    url = getattr(img, "url", "") or (img.get("url", "") if isinstance(img, dict) else "")
    http_status = getattr(img, "http_status", 0) or (img.get("http_status", 0) if isinstance(img, dict) else 0)
    
    if not url or url.strip() == "":
        return True
    
    # Check for placeholder patterns
    url_lower = url.lower()
    if any(p in url_lower for p in ["placeholder", "data:image", "blank", "spacer", "1x1", "pixel"]):
        return True
    
    # Check HTTP status
    if http_status and http_status >= 400:
        return True
    
    return False


def analyze_images(images: list) -> dict:
    """
    Analyze a list of ImageData objects and return comprehensive metrics.
    
    Returns dict with all metrics needed by the 14 image SEO rules.
    """
    if not images:
        return {
            "total_images": 0,
            "total_sources": 0,
            "total_pictures": 0,
            "with_alt": 0,
            "without_alt": 0,
            "decorative_images": 0,
            "generic_alt_count": 0,
            "descriptive_alt_count": 0,
            "alt_length_min": 0,
            "alt_length_max": 0,
            "alt_length_avg": 0.0,
            "has_width_attr": 0,
            "has_height_attr": 0,
            "missing_dimensions": 0,
            "has_srcset_count": 0,
            "has_sizes_count": 0,
            "has_modern_format": False,
            "modern_format_count": 0,
            "legacy_format_count": 0,
            "has_lazy_loading_count": 0,
            "above_fold_count": 0,
            "below_fold_count": 0,
            "below_fold_missing_lazy": 0,
            "has_picture_element": False,
            "picture_without_img_fallback": 0,
            "has_figcaption": False,
            "figure_count": 0,
            "image_count_without_caption": 0,
            "css_background_image_count": 0,
            "inline_svg_count": 0,
            "inline_svg_total_size_kb": 0,
            "oversized_image_count": 0,
            "broken_image_count": 0,
            "generic_filename_count": 0,
            "descriptive_filename_count": 0,
            "has_fetchpriority_high": False,
            "aspect_ratio_mismatch_count": 0,
            "thumbnails_with_large_files": 0,
            "alt_coverage_percent": 0.0,
            "has_lazy_loading": False,
        }

    total = len(images)
    alt_lengths = []
    src_count = 0  # for above/below fold heuristic
    
    with_alt = 0
    without_alt = 0
    decorative = 0
    generic_alt = 0
    descriptive_alt = 0
    has_width = 0
    has_height = 0
    missing_dims = 0
    has_srcset = 0
    has_sizes = 0
    modern_format = 0
    legacy_format = 0
    lazy_loading = 0
    picture_fallback_missing = 0
    css_bg = 0
    inline_svg = 0
    svg_size_kb = 0
    oversized = 0
    broken = 0
    generic_fn = 0
    descriptive_fn = 0
    fetchpriority_high = False
    aspect_mismatch = 0
    thumb_large = 0
    
    for idx, img in enumerate(images):
        # Get attributes safely (handle both object and dict)
        if hasattr(img, "alt"):
            alt = img.alt
            url = img.url
            tag = img.tag
            loading = img.loading
            width = img.width
            height = img.height
            srcset = img.srcset
            sizes = img.sizes
            fetchpriority = getattr(img, "fetchpriority", "")
            is_decorative = getattr(img, "is_decorative", False)
            is_bg = getattr(img, "is_background_image", False)
            natural_w = getattr(img, "natural_width", 0)
            natural_h = getattr(img, "natural_height", 0)
            file_size = getattr(img, "file_size_bytes", 0)
            http_status = getattr(img, "http_status", 0)
        else:
            alt = img.get("alt", "")
            url = img.get("url", "")
            tag = img.get("tag", "")
            loading = img.get("loading", "")
            width = img.get("width", "")
            height = img.get("height", "")
            srcset = img.get("srcset", "")
            sizes = img.get("sizes", "")
            fetchpriority = img.get("fetchpriority", "")
            is_decorative = img.get("is_decorative", False)
            is_bg = img.get("is_background_image", False)
            natural_w = img.get("natural_width", 0)
            natural_h = img.get("natural_height", 0)
            file_size = img.get("file_size_bytes", 0)
            http_status = img.get("http_status", 0)
        
        if tag in ("img", "source") or (not tag and url):
            src_count += 1
            
            # Alt text analysis
            if alt and alt.strip():
                with_alt += 1
                alt_len = len(alt.strip())
                alt_lengths.append(alt_len)
                
                if is_decorative:
                    decorative += 1
                elif _is_generic_alt(alt):
                    generic_alt += 1
                else:
                    descriptive_alt += 1
            else:
                without_alt += 1
            
            # Dimensions
            if width and width.strip():
                has_width += 1
            if height and height.strip():
                has_height += 1
            if not (width and width.strip() and height and height.strip()):
                missing_dims += 1
            
            # Responsive attributes
            if srcset:
                has_srcset += 1
            if sizes:
                has_sizes += 1
            
            # Format detection
            if _is_modern_format(url):
                modern_format += 1
            elif url:
                legacy_format += 1
            
            # Lazy loading
            if _has_lazy_loading(img):
                lazy_loading += 1
            
            # Broken image
            if _is_broken_image(img):
                broken += 1
            
            # Oversized
            if file_size and file_size > 200 * 1024:  # > 200KB
                oversized += 1
            
            # Filename quality
            filename = _get_filename(url)
            if filename:
                if _is_generic_filename(filename):
                    generic_fn += 1
                else:
                    descriptive_fn += 1
            
            # Fetchpriority
            if fetchpriority.strip().lower() == "high":
                fetchpriority_high = True
            
            # Aspect ratio mismatch (attribute vs intrinsic)
            if width and height and natural_w and natural_h:
                try:
                    w_attr = int(width)
                    h_attr = int(height)
                    if w_attr > 0 and h_attr > 0 and natural_w > 0 and natural_h > 0:
                        attr_ratio = w_attr / h_attr
                        intrinsic_ratio = natural_w / natural_h
                        if abs(attr_ratio - intrinsic_ratio) > 0.1:  # 10% tolerance
                            aspect_mismatch += 1
                except (ValueError, ZeroDivisionError):
                    pass
            
            # Thumbnail with large file (rendered small but source large)
            if width and height and file_size:
                try:
                    w_attr = int(width)
                    h_attr = int(height)
                    if w_attr < 200 and h_attr < 200 and file_size > 50 * 1024:  # > 50KB
                        thumb_large += 1
                except ValueError:
                    pass
        
        elif tag == "picture_missing_fallback":
            picture_fallback_missing += 1
        
        elif tag == "css_background":
            css_bg += 1
        
        elif tag == "svg" or (url and url.endswith(".svg") and "svg" in str(getattr(img, "attributes", {}))):
            inline_svg += 1
            if file_size:
                svg_size_kb += file_size / 1024
    
    # Above/below fold heuristic: first 3 images are above fold
    above_fold = min(3, src_count)
    below_fold = max(0, src_count - 3)
    below_fold_missing_lazy = max(0, below_fold - lazy_loading)
    
    alt_length_min = min(alt_lengths) if alt_lengths else 0
    alt_length_max = max(alt_lengths) if alt_lengths else 0
    alt_length_avg = sum(alt_lengths) / len(alt_lengths) if alt_lengths else 0.0
    
    # Picture elements
    has_picture = any(
        (getattr(img, "tag", "") if hasattr(img, "tag") else img.get("tag", "")) in ("source", "picture_missing_fallback")
        for img in images
    )
    
    return {
        "total_images": total,
        "total_sources": sum(1 for img in images if (getattr(img, "tag", "") if hasattr(img, "tag") else img.get("tag", "")) == "source"),
        "total_pictures": picture_fallback_missing,  # synthetic record per picture
        "with_alt": with_alt,
        "without_alt": without_alt,
        "decorative_images": decorative,
        "generic_alt_count": generic_alt,
        "descriptive_alt_count": descriptive_alt,
        "alt_length_min": alt_length_min,
        "alt_length_max": alt_length_max,
        "alt_length_avg": round(alt_length_avg, 1),
        "alt_coverage_percent": round((with_alt / src_count * 100) if src_count > 0 else 0.0, 1),
        "has_width_attr": has_width,
        "has_height_attr": has_height,
        "missing_dimensions": missing_dims,
        "has_srcset_count": has_srcset,
        "has_sizes_count": has_sizes,
        "has_modern_format": modern_format > 0,
        "modern_format_count": modern_format,
        "legacy_format_count": legacy_format,
        "has_lazy_loading_count": lazy_loading,
        "has_lazy_loading": lazy_loading > 0,
        "above_fold_count": above_fold,
        "below_fold_count": below_fold,
        "below_fold_missing_lazy": below_fold_missing_lazy,
        "has_picture_element": has_picture,
        "picture_without_img_fallback": picture_fallback_missing,
        "has_figcaption": False,  # Would need figure/figcaption extraction from content
        "figure_count": 0,
        "image_count_without_caption": 0,
        "css_background_image_count": css_bg,
        "inline_svg_count": inline_svg,
        "inline_svg_total_size_kb": round(svg_size_kb, 1),
        "oversized_image_count": oversized,
        "broken_image_count": broken,
        "generic_filename_count": generic_fn,
        "descriptive_filename_count": descriptive_fn,
        "has_fetchpriority_high": fetchpriority_high,
        "aspect_ratio_mismatch_count": aspect_mismatch,
        "thumbnails_with_large_files": thumb_large,
    }