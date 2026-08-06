"""
Checksum utility for generating page/content checksums.
"""
import hashlib


def generate_checksum(content: bytes) -> str:
    """
    Generate SHA-256 checksum for content.
    
    Args:
        content: Content bytes to checksum
        
    Returns:
        Hexadecimal checksum string
    """
    return hashlib.sha256(content).hexdigest()