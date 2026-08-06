"""
HTML compression/minification utility.
"""
from typing import Optional


def compress_html(html: str) -> str:
    """
    Compress HTML by removing unnecessary whitespace.
    
    Args:
        html: Raw HTML string
        
    Returns:
        Compressed HTML string
    """
    # Remove leading/trailing whitespace from each line
    lines = html.split('\n')
    compressed_lines = [line.strip() for line in lines if line.strip()]
    
    # Join with single space
    compressed = ' '.join(compressed_lines)
    
    # Remove multiple spaces
    while '  ' in compressed:
        compressed = compressed.replace('  ', ' ')
    
    return compressed


def should_compress(html: str, threshold: int = 1024) -> bool:
    """
    Check if HTML should be compressed based on size.
    
    Args:
        html: Raw HTML string
        threshold: Minimum size in bytes to compress
        
    Returns:
        True if should compress, False otherwise
    """
    return len(html.encode('utf-8')) > threshold