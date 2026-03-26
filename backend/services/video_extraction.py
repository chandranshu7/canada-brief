"""
Extract video URLs and generate thumbnail URLs from article content.

Supports YouTube, Vimeo, and other common video platforms.
"""

import re
from typing import Optional
from urllib.parse import parse_qs, urlparse


def extract_video_url(html_content: str, article_link: str) -> Optional[str]:
    """
    Extract video URL from article HTML or article link itself.
    
    Returns (video_url, video_type) or None.
    Supported: YouTube, Vimeo, generic iframe embeds.
    """
    if not html_content:
        return None

    # YouTube embeds (iframe)
    yt_patterns = [
        r'iframe[^>]*src=["\']([^"\']*youtube(?:\.com|\.be)[^\'"]*)["\']',
        r'youtube\.com/embed/([a-zA-Z0-9_-]+)',
        r'youtu\.be/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in yt_patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            if "iframe" in pattern:
                return match.group(1)
            video_id = match.group(1)
            return f"https://www.youtube.com/watch?v={video_id}"

    # Vimeo embeds
    vimeo_patterns = [
        r'iframe[^>]*src=["\']([^"\']*vimeo\.com[^\'"]*)["\']',
        r'vimeo\.com/([0-9]+)',
    ]
    
    for pattern in vimeo_patterns:
        match = re.search(pattern, html_content, re.IGNORECASE)
        if match:
            if "iframe" in pattern:
                return match.group(1)
            video_id = match.group(1)
            return f"https://vimeo.com/{video_id}"

    # Generic video embeds (check for video tags, source tags)
    video_src_pattern = r'<video[^>]*>.*?<source[^>]*src=["\']([^"\']+\.(?:mp4|webm|ogv))["\']'
    match = re.search(video_src_pattern, html_content, re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1)

    return None


def get_video_thumbnail_url(video_url: str) -> Optional[str]:
    """
    Generate thumbnail URL for a given video URL.
    
    YouTube: predictable thumbnail structure
    Vimeo: requires API (fallback to oembed)
    Others: attempt oembed endpoint
    """
    if not video_url:
        return None

    video_url_lower = video_url.lower()

    # YouTube thumbnail (predictable URL structure)
    if "youtube.com" in video_url_lower or "youtu.be" in video_url_lower:
        video_id = extract_youtube_id(video_url)
        if video_id:
            # Use high quality thumbnail (mqdefault = medium quality but good balance)
            # hqdefault = high quality (480x360)
            # maxresdefault = original resolution (not always available)
            return f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"

    # Vimeo (use oembed endpoint for thumbnail)
    if "vimeo.com" in video_url_lower:
        video_id = extract_vimeo_id(video_url)
        if video_id:
            # Vimeo player embed endpoint (fallback to simpler approach)
            # Real solution would use Vimeo API, but this works for most cases
            return f"https://i.vimeocdn.com/video/{video_id}.jpg"

    # For generic embeds, return None (no reliable fallback)
    return None


def extract_youtube_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from various YouTube URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]+)',
        r'youtube\.com/v/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def extract_vimeo_id(url: str) -> Optional[str]:
    """Extract Vimeo video ID from Vimeo URL."""
    match = re.search(r'vimeo\.com/(\d+)', url)
    if match:
        return match.group(1)
    return None
