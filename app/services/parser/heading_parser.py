"""Heading Parser - Extracts and analyzes heading tags (H1-H6)."""
from typing import Dict, Any, List
from bs4 import BeautifulSoup


class HeadingParser:
    """Extracts and analyzes heading structure."""
    
    @staticmethod
    def get_headings(soup: BeautifulSoup) -> Dict[str, List[str]]:
        """
        Extract all headings from page.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Dictionary with heading levels as keys and list of heading text as values
        """
        headings = {}
        
        for level in range(1, 7):
            tag = f'h{level}'
            heading_tags = soup.find_all(tag)
            headings[tag] = [h.get_text(strip=True) for h in heading_tags if h.get_text(strip=True)]
        
        return headings
    
    @staticmethod
    def get_heading_stats(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Get statistics about headings.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Heading statistics
        """
        headings = HeadingParser.get_headings(soup)
        
        stats = {
            "h1_count": len(headings.get('h1', [])),
            "h2_count": len(headings.get('h2', [])),
            "h3_count": len(headings.get('h3', [])),
            "h4_count": len(headings.get('h4', [])),
            "h5_count": len(headings.get('h5', [])),
            "h6_count": len(headings.get('h6', [])),
            "total_headings": sum(len(v) for v in headings.values()),
            "has_h1": len(headings.get('h1', [])) > 0,
            "multiple_h1": len(headings.get('h1', [])) > 1
        }
        
        return stats
    
    @staticmethod
    def validate_heading_structure(soup: BeautifulSoup) -> Dict[str, Any]:
        """
        Validate heading hierarchy.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Validation results
        """
        headings = []
        
        # Get all headings with their levels
        for level in range(1, 7):
            for tag in soup.find_all(f'h{level}'):
                headings.append({
                    "level": level,
                    "text": tag.get_text(strip=True)
                })
        
        issues = []
        
        if not headings:
            issues.append("No headings found")
            return {"valid": False, "issues": issues}
        
        # Check for H1
        h1_count = sum(1 for h in headings if h['level'] == 1)
        if h1_count == 0:
            issues.append("Missing H1 tag")
        elif h1_count > 1:
            issues.append(f"Multiple H1 tags found ({h1_count})")
        
        # Check hierarchy (headings should not skip levels)
        for i in range(len(headings) - 1):
            current_level = headings[i]['level']
            next_level = headings[i + 1]['level']
            
            # Allow skipping down by 1 level max
            if next_level > current_level + 1:
                issues.append(
                    f"Heading level skipped: H{current_level} -> H{next_level}"
                )
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "heading_count": len(headings),
            "h1_count": h1_count
        }