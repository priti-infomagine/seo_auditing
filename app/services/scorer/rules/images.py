"""
Image SEO Rules.
"""
from typing import Any, Dict, List

from app.services.scorer.base_rule import BaseRule
from app.models.scorer_models.rule_result import RuleResult, Severity


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
            severity=Severity.WARNING,
            score_impact=impact,
            recommendation=f"Add descriptive alt text to {without_alt} images",
            data={"total_count": total_count, "without_alt": without_alt, "coverage": coverage},
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
            size = img.get("file_size", 0)
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
        lazy_loading = images.get("lazy_loading", False)
        total_count = images.get("total_count", 0)
        
        if total_count == 0:
            return [self._create_result(
                passed=True,
                message="No images found",
                severity=Severity.INFO,
                score_impact=0,
            )]
        
        if lazy_loading:
            return [self._create_result(
                passed=True,
                message="Lazy loading is implemented",
                severity=Severity.PASSED,
                score_impact=1,
                data={"lazy_loading": True},
            )]
        
        return [self._create_result(
            passed=False,
            message="Lazy loading not detected",
            severity=Severity.INFO,
            score_impact=-1,
            recommendation="Add loading='lazy' attribute to images below the fold",
            data={"lazy_loading": False},
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