"""Image Parser - Extracts and analyzes images."""
from typing import Dict, Any, List
from bs4 import BeautifulSoup


class ImageParser:
    """Extracts and analyzes images."""
    
    @staticmethod
    def get_images(soup: BeautifulSoup, base_url: str = "") -> Dict[str, Any]:
        """
        Extract all images from page.
        
        Args:
            soup: BeautifulSoup object
            base_url: Base URL for resolving relative paths
            
        Returns:
            Dictionary containing image analysis
        """
        images = []
        images_without_alt = 0
        
        # Find all img tags
        for img in soup.find_all('img'):
            src = img.get('src', '').strip()
            if not src:
                continue
            
            alt_text = img.get('alt', '')
            has_alt = bool(alt_text and alt_text.strip())
            
            if not has_alt:
                images_without_alt += 1
            
            image_data = {
                "src": src,
                "alt": alt_text,
                "has_alt": has_alt,
                "title": img.get('title', ''),
                "width": img.get('width', ''),
                "height": img.get('height', ''),
                "loading": img.get('loading', 'lazy' in str(img.get('loading', '')))
            }
            
            images.append(image_data)
        
        total_count = len(images)
        
        return {
            "total_count": total_count,
            "without_alt": images_without_alt,
            "with_alt": total_count - images_without_alt,
            "sample": images[:10],
            "lazy_loading": any(img.get('loading', False) for img in images) if images else False
        }
    
    @staticmethod
    def get_image_count(soup: BeautifulSoup) -> int:
        """
        Get total image count.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Number of images
        """
        return len(soup.find_all('img'))
    
    @staticmethod
    def get_images_without_alt(soup: BeautifulSoup) -> int:
        """
        Count images missing alt text.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Number of images without alt text
        """
        count = 0
        for img in soup.find_all('img'):
            alt = img.get('alt', '').strip()
            if not alt:
                count += 1
        return count
    
    @staticmethod
    def get_image_alt_coverage(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Calculate alt text coverage statistics.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Coverage statistics
        """
        total = ImageParser.get_image_count(soup)
        without_alt = ImageParser.get_images_without_alt(soup)
        with_alt = total - without_alt
        
        coverage_percent = (with_alt / total * 100) if total > 0 else 0.0
        
        return {
            "total_images": total,
            "with_alt": with_alt,
            "without_alt": without_alt,
            "coverage_percent": round(coverage_percent, 1),
            "status": "Good" if without_alt == 0 else "Needs Improvement"
        }
    
    @staticmethod
    def has_lazy_loading(soup: BeautifulSoup) -> bool:
        """
        Check if lazy loading is implemented.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            True if lazy loading detected
        """
        # Check for loading="lazy" attribute
        lazy_images = soup.find_all('img', loading='lazy')
        if lazy_images:
            return True
        
        # Check for noscript tags (lazy loading fallback)
        noscript_tags = soup.find_all('noscript')
        if any('img' in str(tag).lower() for tag in noscript_tags):
            return True
        
        return False