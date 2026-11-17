"""
Image SEO Rules.
"""
from typing import Any, Dict, List

from app.modules.scorer.services.base_rule import BaseRule
from app.modules.rule_engine.models.rule_result import RuleResult, Severity


class ImageAltTextRule(BaseRule):
    """Check image alt text coverage."""
    rule_id = "images_001"
    name = "Image Alt Text"
    category = "images"
    description = "All images should have descriptive alt text"
    weight = 1.2
    tags = ["critical", "images", "accessibility"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        total_count = images.get("total_count", 0)
        without_alt = images.get("without_alt", 0)
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No images found on page",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        with_alt = total_count - without_alt
        coverage = (with_alt / total_count * 100) if total_count > 0 else 0
        
        if without_alt == 0:
            return [self._create_result(
                passed=True,
                message=f"All {total_count} images have alt text",
                severity=Severity.PASSED,
                score_impact=1,
                data={"total_count": total_count, "with_alt": with_alt},
            )]
        
        if coverage >= 80:
            return [self._create_result(
                passed=True,
                message=f"Good alt text coverage: {coverage:.1f}% ({without_alt} missing)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"total_count": total_count, "without_alt": without_alt, "coverage": coverage},
            )]
        
        impact = -min(without_alt * 2, 10)
        return [self._create_result(
            passed=False,
            message=f"{without_alt}/{total_count} images missing alt text ({coverage:.1f}% coverage)",
            severity=Severity.INFO,
            score_impact=impact,
            recommendation=f"Add descriptive alt text to {without_alt} images",
            data={"total_count": total_count, "without_alt": without_alt, "coverage": coverage, "sample": images.get("sample", [])},
        )]


class ImageSizeRule(BaseRule):
    """Check image file sizes."""
    rule_id = "images_002"
    name = "Image File Size"
    category = "images"
    description = "Images should be optimized for web"
    weight = 0.9
    tags = ["warning", "images", "performance"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        image_data = images.get("sample", [])
        
        if not image_data:
            return [self._create_result(
                passed=True,
                message="No image size data available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        large_images = []
        for img in image_data[:10]:  # Check first 10
            size = img.get("file_size", img.get("file_size_bytes", 0))
            if size > 500000:  # 500KB
                large_images.append({
                    "src": img.get("src", ""),
                    "size_kb": size / 1024,
                })
        
        if not large_images:
            return [self._create_result(
                passed=True,
                message="All images are reasonably sized",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{len(large_images)} images are large (>500KB)",
            severity=Severity.WARNING,
            score_impact=-3,
            recommendation="Compress large images or use next-gen formats (WebP, AVIF)",
            data={"large_images": large_images[:5]},
        )]


# class LazyLoadingRule(BaseRule):
#     """Check for lazy loading implementation."""
#     rule_id = "images_003"
#     name = "Lazy Loading"
#     category = "images"
#     description = "Images should use lazy loading for performance"
#     weight = 0.8
#     tags = ["info", "images", "performance"]
    
#     async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
#         images = data.get("images", {})
#         lazy_count = images.get("has_lazy_loading_count", 0)
#         total_count = images.get("total_count", 0)
#         below_fold = images.get("below_fold_count", 0)
#         below_fold_missing = images.get("below_fold_missing_lazy", 0)
        
#         if total_count == 0:
#             return [self._create_result(
#                 passed=True,
#                 message="No images found on page",
#                 severity=Severity.INFO,
#                 score_impact=0,
#             )]
        
#         if lazy_count > 0:
#             return [self._create_result(
#                 passed=True,
#                 message=f"Lazy loading is implemented ({lazy_count} images with loading='lazy')",
#                 severity=Severity.PASSED,
#                 score_impact=1,
#                 data={"lazy_loading": True, "lazy_count": lazy_count},
#             )]
        
        # if below_fold_missing > 0:
        #     return [self._create_result(
        #         passed=False,
        #         message=f"{below_fold_missing} below-fold images missing loading='lazy'",
        #         severity=Severity.WARNING,
        #         score_impact=-min(below_fold_missing, 5),
        #         recommendation="Add loading='lazy' attribute to images below the fold",
        #         data={"lazy_loading": False, "below_fold_missing": below_fold_missing},
        #     )]
        
        # return [self._create_result(
        #     passed=False,
        #     message="Lazy loading not detected on any image",
        #     severity=Severity.INFO,
        #     score_impact=-1,
        #     recommendation="Add loading='lazy' attribute to images below the fold",
        #     data={"lazy_loading": False},
        # )]

class LazyLoadingRule(BaseRule):
    """Check for lazy loading implementation."""
    rule_id = "images_003"
    name = "Lazy Loading"
    category = "images"
    description = "Images should use lazy loading for performance"
    weight = 0.8
    tags = ["info", "images", "performance"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        lazy_count = images.get("has_lazy_loading_count", 0)
        total_count = images.get("total_count", 0)
        below_fold = images.get("below_fold_count", 0)
        below_fold_missing = images.get("below_fold_missing_lazy", 0)
        sample = images.get("sample", [])
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No images found on page",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if lazy_count > 0:
            return [self._create_result(
                passed=True,
                message=f"Lazy loading is implemented ({lazy_count} images with loading='lazy')",
                severity=Severity.PASSED,
                score_impact=1,
                data={"lazy_loading": True, "lazy_count": lazy_count},
            )]
        
        # Collect image URLs missing lazy loading from sample
        missing_lazy_images = []
        for img in sample:
            loading = img.get("loading", "").strip().lower()
            if loading != "lazy":
                src = img.get("src") or img.get("url", "")
                if src:
                    missing_lazy_images.append({
                        "image_url": src,
                        "alt": img.get("alt", ""),
                        "width": img.get("width", ""),
                        "height": img.get("height", ""),
                    })
        
        if below_fold_missing > 0:
            return [self._create_result(
                passed=False,
                message=f"{below_fold_missing} below-fold images missing loading='lazy'",
                severity=Severity.WARNING,
                score_impact=-min(below_fold_missing, 5),
                recommendation="Add loading='lazy' attribute to images below the fold",
                data={
                    "lazy_loading": False, 
                    "below_fold_missing": below_fold_missing,
                    "missing_lazy_images": missing_lazy_images[:20],  # cap at 20
                },
            )]
        
        return [self._create_result(
            passed=False,
            message="Lazy loading not detected on any image",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add loading='lazy' attribute to images below the fold",
            data={
                "lazy_loading": False,
                "missing_lazy_images": missing_lazy_images[:20],
            },
        )]



class ImageDimensionsRule(BaseRule):
    """Check if images have width/height attributes."""
    rule_id = "images_004"
    name = "Image Dimensions"
    category = "images"
    description = "Images should have width and height attributes to prevent layout shift"
    weight = 0.7
    tags = ["warning", "images", "ux", "core_web_vitals"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        image_data = images.get("sample", [])
        
        if not image_data:
            return [self._create_result(
                passed=True,
                message="No image dimension data available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        missing_dimensions = 0
        for img in image_data[:10]:
            has_width = img.get("width") or img.get("width_attr")
            has_height = img.get("height") or img.get("height_attr")
            if not has_width or not has_height:
                missing_dimensions += 1
        
        if missing_dimensions == 0:
            return [self._create_result(
                passed=True,
                message="All images have width/height attributes",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message=f"{missing_dimensions} images missing width/height attributes",
            severity=Severity.WARNING,
            score_impact=-2,
            recommendation="Add width and height attributes to prevent Cumulative Layout Shift (CLS)",
            data={"missing_dimensions": missing_dimensions},
        )]


class ResponsiveImagesRule(BaseRule):
    """Check for responsive image implementation."""
    rule_id = "images_005"
    name = "Responsive Images"
    category = "images"
    description = "Check for srcset and sizes attributes"
    weight = 0.6
    tags = ["info", "images", "responsive"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        image_data = images.get("sample", [])
        
        if not image_data:
            return [self._create_result(
                passed=True,
                message="No image data available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        has_srcset = any(img.get("srcset") for img in image_data)
        
        if has_srcset:
            return [self._create_result(
                passed=True,
                message="Responsive images (srcset) detected",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="No responsive images (srcset) detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Consider using srcset and sizes for responsive images",
        )]


class ImageFormatsRule(BaseRule):
    """Check for modern image formats."""
    rule_id = "images_006"
    name = "Modern Image Formats"
    category = "images"
    description = "Check for WebP, AVIF or other modern formats"
    weight = 0.5
    tags = ["info", "images", "performance"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        image_data = images.get("sample", [])
        
        if not image_data:
            return [self._create_result(
                passed=True,
                message="No image data available",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        modern_formats = {"webp", "avif", "jpeg2000", "jxl"}
        has_modern = any(
            any(fmt in img.get("src", "").lower() for fmt in modern_formats)
            for img in image_data
        )
        
        if has_modern:
            return [self._create_result(
                passed=True,
                message="Modern image formats detected (WebP/AVIF)",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        return [self._create_result(
            passed=False,
            message="Only traditional image formats detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Consider using WebP or AVIF for better compression",
        )]


# ================================================================
# NEW RULES (8 additional rules for 14 total)
# ================================================================

class ImageAltQualityRule(BaseRule):
    """Check for generic/non-descriptive alt text."""
    rule_id = "images_007"
    name = "Image Alt Text Quality"
    category = "images"
    description = "Alt text should be descriptive, not generic (e.g., 'image', 'photo', 'banner')"
    weight = 1.0
    tags = ["warning", "images", "accessibility"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        total_count = images.get("total_count", 0)
        generic_count = images.get("generic_alt_count", 0)
        descriptive_count = images.get("descriptive_alt_count", 0)
        decorative_count = images.get("decorative_images", 0)
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No images found on page",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if generic_count == 0:
            return [self._create_result(
                passed=True,
                message=f"All {descriptive_count} content images have descriptive alt text ({decorative_count} decorative)",
                severity=Severity.PASSED,
                score_impact=1,
                data={"descriptive": descriptive_count, "decorative": decorative_count},
            )]
        
        impact = -min(generic_count * 2, 8)
        return [self._create_result(
            passed=False,
            message=f"{generic_count} images have generic/non-descriptive alt text (e.g., 'image', 'photo', 'banner')",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Replace generic alt text with descriptive text that conveys the image's content and purpose",
            data={"generic_count": generic_count, "descriptive_count": descriptive_count, "decorative_count": decorative_count},
        )]


class ImageFilenameQualityRule(BaseRule):
    """Check for descriptive filenames."""
    rule_id = "images_008"
    name = "Image Filename Quality"
    category = "images"
    description = "Image filenames should be descriptive (e.g., 'blue-running-shoes.jpg' not 'IMG_1234.jpg')"
    weight = 0.7
    tags = ["info", "images", "seo"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        generic_count = images.get("generic_filename_count", 0)
        descriptive_count = images.get("descriptive_filename_count", 0)
        total = generic_count + descriptive_count
        
        if total == 0:
            return [self._create_result(
                passed=True,
                message="No images to evaluate",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if generic_count == 0:
            return [self._create_result(
                passed=True,
                message=f"All {descriptive_count} images have descriptive filenames",
                severity=Severity.PASSED,
                score_impact=1,
                data={"descriptive": descriptive_count},
            )]
        
        impact = -min(generic_count, 5)
        return [self._create_result(
            passed=False,
            message=f"{generic_count}/{total} images have generic filenames (e.g., IMG_1234.jpg, screenshot.png)",
            severity=Severity.INFO,
            score_impact=impact,
            recommendation="Rename files descriptively using keywords (e.g., blue-running-shoes.jpg)",
            data={"generic_count": generic_count, "descriptive_count": descriptive_count},
        )]


class FigureCaptionsRule(BaseRule):
    """Check for figure/figcaption usage."""
    rule_id = "images_009"
    name = "Figure Captions Present"
    category = "images"
    description = "Images should use <figure> with <figcaption> for semantic captions"
    weight = 0.5
    tags = ["info", "images", "accessibility", "semantics"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        figure_count = images.get("figure_count", 0)
        has_caption = images.get("has_figcaption", False)
        without_caption = images.get("image_count_without_caption", 0)
        total = images.get("total_count", 0)
        
        if total == 0:
            return [self._create_result(
                passed=True,
                message="No images found on page",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if figure_count == 0:
            return [self._create_result(
                passed=True,
                message="No <figure> elements found (optional for decorative images)",
                severity=Severity.INFO,
                score_impact=0,
                data={"standalone_images": total},
            )]
        
        if without_caption == 0 and has_caption:
            return [self._create_result(
                passed=True,
                message=f"All {figure_count} figure(s) have <figcaption> captions",
                severity=Severity.PASSED,
                score_impact=1,
                data={"figures": figure_count, "with_caption": figure_count},
            )]
        
        impact = -without_caption
        return [self._create_result(
            passed=False,
            message=f"{without_caption}/{figure_count} figure(s) missing <figcaption> captions",
            severity=Severity.INFO,
            score_impact=impact,
            recommendation="Add <figcaption> inside <figure> elements to provide semantic captions",
            data={"figures": figure_count, "with_caption": figure_count - without_caption, "without_caption": without_caption},
        )]


class InlineSVGSizeRule(BaseRule):
    """Check inline SVG size."""
    rule_id = "images_010"
    name = "Inline SVG Size"
    category = "images"
    description = "Inline SVGs should be under 100KB; larger ones should be external files"
    weight = 0.6
    tags = ["warning", "images", "performance"]
    
    MAX_SVG_SIZE_KB = 100
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        svg_count = images.get("inline_svg_count", 0)
        total_size_kb = images.get("inline_svg_total_size_kb", 0)
        
        if svg_count == 0:
            return [self._create_result(
                passed=True,
                message="No inline SVGs found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        avg_size = total_size_kb / svg_count if svg_count > 0 else 0
        
        if total_size_kb <= self.MAX_SVG_SIZE_KB:
            return [self._create_result(
                passed=True,
                message=f"All {svg_count} inline SVGs are under {self.MAX_SVG_SIZE_KB}KB (total: {total_size_kb:.1f}KB)",
                severity=Severity.PASSED,
                score_impact=0,
                data={"svg_count": svg_count, "total_size_kb": total_size_kb},
            )]
        
        impact = -min(svg_count, 3)
        return [self._create_result(
            passed=False,
            message=f"{svg_count} inline SVG(s) total {total_size_kb:.1f}KB (avg {avg_size:.1f}KB) — consider moving large SVGs to external files",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Move large inline SVGs to external .svg files for browser caching",
            data={"svg_count": svg_count, "total_size_kb": total_size_kb, "avg_size_kb": round(avg_size, 1)},
        )]


class PictureFallbackRule(BaseRule):
    """Check for <img> fallback in <picture>."""
    rule_id = "images_011"
    name = "Picture Element Fallback"
    category = "images"
    description = "Every <picture> element must contain an <img> child as fallback"
    weight = 1.0
    tags = ["critical", "images", "compatibility"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        picture_count = images.get("total_pictures", 0)
        missing_fallback = images.get("picture_without_img_fallback", 0)
        has_picture = images.get("has_picture_element", False)
        
        if not has_picture:
            return [self._create_result(
                passed=True,
                message="No <picture> elements found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if missing_fallback == 0:
            return [self._create_result(
                passed=True,
                message=f"All {picture_count} <picture> element(s) have <img> fallback",
                severity=Severity.PASSED,
                score_impact=1,
                data={"pictures": picture_count},
            )]
        
        impact = -missing_fallback * 5
        return [self._create_result(
            passed=False,
            message=f"{missing_fallback}/{picture_count} <picture> element(s) missing <img> fallback — renders nothing in unsupported browsers",
            severity=Severity.CRITICAL,
            score_impact=impact,
            recommendation="Add <img> as the last child inside every <picture> element",
            data={"pictures": picture_count, "missing_fallback": missing_fallback},
        )]


class ImageDimensionsSizeRule(BaseRule):
    """Check for images exceeding 2000px in any dimension."""
    rule_id = "images_012"
    name = "Image Dimensions Size"
    category = "images"
    description = "Images should not exceed 2000px in width or height (wastes bandwidth)"
    weight = 0.6
    tags = ["warning", "images", "performance"]
    
    MAX_DIMENSION = 2000
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        oversized = images.get("oversized_image_count", 0)
        # We'd need the actual dimensions from sample data
        sample = images.get("sample", [])
        
        oversized_details = []
        for img in sample:
            nat_w = img.get("natural_width", 0)
            nat_h = img.get("natural_height", 0)
            if nat_w > self.MAX_DIMENSION or nat_h > self.MAX_DIMENSION:
                oversized_details.append({
                    "src": img.get("src", ""),
                    "width": nat_w,
                    "height": nat_h,
                })
        
        if not oversized_details and oversized == 0:
            return [self._create_result(
                passed=True,
                message=f"No images exceed {self.MAX_DIMENSION}px in width or height",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        count = len(oversized_details) or oversized
        impact = -min(count * 2, 8)
        return [self._create_result(
            passed=False,
            message=f"{count} image(s) exceed {self.MAX_DIMENSION}px in width or height",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation=f"Resize images to max {self.MAX_DIMENSION}px; serve appropriately sized images via srcset",
            data={"oversized": oversized_details},
        )]


class BrokenImageDetectionRule(BaseRule):
    """Detect broken image sources."""
    rule_id = "images_013"
    name = "Broken Image Detection"
    category = "images"
    description = "Image sources should be valid (HTTP 2xx, non-empty, not placeholder)"
    weight = 1.2
    tags = ["critical", "images", "ux"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        broken_count = images.get("broken_image_count", 0)
        total = images.get("total_count", 0)
        
        if total == 0:
            return [self._create_result(
                passed=True,
                message="No images found on page",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if broken_count == 0:
            return [self._create_result(
                passed=True,
                message=f"All {total} image sources are valid",
                severity=Severity.PASSED,
                score_impact=1,
                data={"checked": total},
            )]
        
        impact = -min(broken_count * 3, 12)
        return [self._create_result(
            passed=False,
            message=f"{broken_count}/{total} image(s) are broken, empty, or placeholder sources",
            severity=Severity.CRITICAL,
            score_impact=impact,
            recommendation="Fix or remove broken image URLs; ensure all image sources return HTTP 2xx",
            data={"broken_count": broken_count, "total_checked": total},
        )]


class CSSBackgroundImagesRule(BaseRule):
    """Detect CSS background images used for content."""
    rule_id = "images_014"
    name = "CSS Background Images for Content"
    category = "images"
    description = "Content images should use <img> tags, not CSS background-image (not indexed by Google Images)"
    weight = 0.8
    tags = ["warning", "images", "seo"]
    
    async def evaluate(self, data: Dict[str, Any]) -> List[RuleResult]:
        images = data.get("images", {})
        css_bg_count = images.get("css_background_image_count", 0)
        
        if css_bg_count == 0:
            return [self._create_result(
                passed=True,
                message="No CSS background images found",
                severity=Severity.PASSED,
                score_impact=0,
            )]
        
        impact = -min(css_bg_count, 5)
        return [self._create_result(
            passed=False,
            message=f"Found {css_bg_count} CSS background-image declaration(s) — content images should use <img> for SEO indexing",
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation="Use <img> tags with alt text for content images; reserve CSS background-image for decorative only",
            data={"css_background_count": css_bg_count},
        )]