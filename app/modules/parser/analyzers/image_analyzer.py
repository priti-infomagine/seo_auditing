from __future__ import annotations


def analyze_images(images: list) -> dict:
    total = len(images)
    with_alt = sum(1 for img in images if img.alt and img.alt.strip())
    without_alt = total - with_alt
    has_lazy = any(img.loading == "lazy" for img in images)

    coverage = round((with_alt / total) * 100, 1) if total > 0 else 0.0

    return {
        "total_images": total,
        "with_alt": with_alt,
        "without_alt": without_alt,
        "alt_coverage_percent": coverage,
        "has_lazy_loading": has_lazy,
    }
