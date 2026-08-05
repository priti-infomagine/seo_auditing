"""
Performance Metrics Collector
==============================
Collects browser performance metrics using Playwright.
"""

from typing import Dict, Any, List


class PerformanceCollector:
    """Collects performance metrics from browser."""
    
    @staticmethod
    def collect_from_page(page) -> Dict[str, Any]:
        """
        Collect performance metrics from Playwright page.
        
        Args:
            page: Playwright page object
            
        Returns:
            Dictionary containing performance metrics
        """
        try:
            # Execute JavaScript to collect performance metrics
            metrics = page.evaluate("""
                () => {
                    const perfData = performance.getEntriesByType('navigation')[0];
                    const paintMetrics = performance.getEntriesByType('paint');
                    
                    const result = {
                        dom_content_loaded: 0,
                        load_event: 0,
                        first_paint: 0,
                        first_contentful_paint: 0,
                        largest_contentful_paint: 0
                    };
                    
                    // Navigation timing
                    if (perfData) {
                        result.dom_content_loaded = perfData.domContentLoadedEventEnd || 0;
                        result.load_event = perfData.loadEventEnd || 0;
                    }
                    
                    // Paint metrics
                    paintMetrics.forEach(entry => {
                        if (entry.name === 'first-paint') {
                            result.first_paint = entry.startTime || 0;
                        } else if (entry.name === 'first-contentful-paint') {
                            result.first_contentful_paint = entry.startTime || 0;
                        }
                    });
                    
                    // Largest Contentful Paint (if available)
                    if (perfData && perfData.largestContentfulPaint) {
                        result.largest_contentful_paint = perfData.largestContentfulPaint || 0;
                    }
                    
                    return result;
                }
            """)
            
            return metrics if isinstance(metrics, dict) else {}
            
        except Exception:
            return {
                "dom_content_loaded": 0,
                "load_event": 0,
                "first_paint": 0,
                "first_contentful_paint": 0,
                "largest_contentful_paint": 0
            }
    
    @staticmethod
    def collect_response_timing(start_time, end_time) -> Dict[str, float]:
        """
        Calculate response timing.
        
        Args:
            start_time: Start timestamp
            end_time: End timestamp
            
        Returns:
            Dictionary with timing information
        """
        if hasattr(start_time, 'total_seconds'):
            total_time = (end_time - start_time).total_seconds()
        else:
            total_time = 0
        
        return {
            "total_seconds": total_time
        }