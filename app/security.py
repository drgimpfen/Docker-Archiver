"""
Security utilities for path validation and sanitization.
"""
import os
from pathlib import Path


def is_safe_path(base_dir, path, follow_symlinks=True):
    """
    Check if a path is safe (no directory traversal).
    
    Args:
        base_dir: The base directory that path should be within
        path: The path to check
        follow_symlinks: Whether to follow symbolic links
    
    Returns:
        bool: True if path is safe, False otherwise
    """
    try:
        # Resolve to absolute paths
        base_dir = Path(base_dir).resolve()
        
        if follow_symlinks:
            path = Path(path).resolve()
        else:
            path = Path(path).absolute()
        
        # Check if path is within base_dir
        return path.is_relative_to(base_dir)
    except (ValueError, OSError):
        return False


def sanitize_filename(filename):
    """
    Sanitize a filename by removing/replacing dangerous characters.
    
    Args:
        filename: The filename to sanitize
    
    Returns:
        str: Sanitized filename
    """
    # Remove path separators and null bytes
    dangerous_chars = ['/', '\\', '\0', '..']
    sanitized = filename
    
    for char in dangerous_chars:
        sanitized = sanitized.replace(char, '_')
    
    # Remove leading/trailing dots and spaces
    sanitized = sanitized.strip('. ')
    
    # Ensure not empty
    if not sanitized:
        sanitized = 'unnamed'
    
    return sanitized


def validate_archive_name(name):
    """
    Validate archive name for safety.
    
    Args:
        name: Archive name to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    if not name or len(name) > 255:
        return False
    
    # Check for dangerous patterns
    dangerous_patterns = ['..', '/', '\\', '\0', '\n', '\r']
    for pattern in dangerous_patterns:
        if pattern in name:
            return False
    
    # Must start with alphanumeric
    if not name[0].isalnum():
        return False
    
    return True
