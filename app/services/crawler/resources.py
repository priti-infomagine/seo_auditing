"""
Resource Tracker
================
Tracks all loaded resources (JS, CSS, images, etc.) during page load.
"""

from typing import Dict, List, Any


class ResourceTracker:
    """Tracks all resources loaded by the browser."""
    
    def __init__(self):
        self.resources: Dict[str, List[Dict[str, Any]]] = {
            "javascript": [],
            "css": [],
            "images": [],
            "fonts": [],
            "documents": [],
            "other": []
        }
    
    def track_resource(self, url: str, resource_type: str, size: int = 0):
        """
        Track a loaded resource.
        
        Args:
            url: Resource URL
            resource_type: Type of resource (javascript, css, images, etc.)
            size: Resource size in bytes
        """
        resource = {
            "url": url,
            "type": resource_type,
            "size": size
        }
        
        # Categorize resource
        if resource_type in ["javascript", "js"]:
            self.resources["javascript"].append(resource)
        elif resource_type in ["css", "stylesheet"]:
            self.resources["css"].append(resource)
        elif resource_type in ["image", "img"]:
            self.resources["images"].append(resource)
        elif resource_type in ["font", "woff", "woff2", "ttf", "otf"]:
            self.resources["fonts"].append(resource)
        elif resource_type in ["document", "html"]:
            self.resources["documents"].append(resource)
        else:
            self.resources["other"].append(resource)
    
    def get_resources(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get all tracked resources."""
        return self.resources
    
    def clear(self):
        """Clear all tracked resources."""
        self.resources = {
            "javascript": [],
            "css": [],
            "images": [],
            "fonts": [],
            "documents": [],
            "other": []
        }
    
    @staticmethod
    def categorize_url(url: str) -> str:
        """
        Categorize resource type from URL.
        
        Args:
            url: Resource URL
            
        Returns:
            Resource type string
        """
        url_lower = url.lower()
        
        if any(ext in url_lower for ext in ['.js', '.javascript']):
            return "javascript"
        elif any(ext in url_lower for ext in ['.css', '.stylesheet']):
            return "css"
        elif any(ext in url_lower for ext in ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico']):
            return "images"
        elif any(ext in url_lower for ext in ['.woff', '.woff2', '.ttf', '.otf', '.eot']):
            return "fonts"
        elif any(ext in url_lower for ext in ['.html', '.htm', '.php', '.asp', '.aspx']):
            return "documents"
        else:
            return "other"