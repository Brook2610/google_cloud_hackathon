"""Website building tools for the AI agent.

Provides file operation tools (write_file, read_file, list_files) and
business context tools for integrating Google Places data.
"""
from pathlib import Path
from typing import List
from langchain_core.tools import tool

from places import fetch_place_details, format_business_context


def make_website_tools(session_dir: Path, biz_ctx: dict = None) -> List:
    """Create website tools bound to a specific session directory.
    
    Args:
        session_dir: Directory for this session's files
        biz_ctx: Optional business context dictionary
    
    Returns:
        List of LangChain tools
    """
    base = session_dir.resolve()
    base.mkdir(parents=True, exist_ok=True)
    
    # Create standard structure
    (base / "public").mkdir(exist_ok=True)
    (base / "public" / "css").mkdir(exist_ok=True)
    (base / "public" / "js").mkdir(exist_ok=True)
    (base / "public" / "images").mkdir(exist_ok=True)
    
    def _safe(filename: str) -> Path:
        """Ensure path is within session directory."""
        p = (base / filename).resolve()
        if not str(p).startswith(str(base)):
            raise ValueError("Invalid path: outside of session directory")
        return p
    
    @tool("list_files")
    def list_files() -> List[str]:
        """List all files in the session directory (excluding hidden files).
        
        Returns:
            List of relative file paths
        """
        files = []
        for f in base.rglob("*"):
            if f.is_file() and not any(part.startswith('.') for part in f.parts):
                files.append(str(f.relative_to(base)))
        return sorted(files)
    
    @tool("read_file")
    def read_file(filename: str) -> str:
        """Read a file's contents from the session directory.
        
        Args:
            filename: Relative path to the file
        
        Returns:
            File contents as string, or error message
        """
        if filename.startswith('.'):
            return "Access denied: system files are hidden."
        try:
            p = _safe(filename)
            if not p.exists():
                return f"File not found: {filename}"
            return p.read_text(encoding="utf-8")
        except Exception as e:
            return f"Error reading {filename}: {e}"
    
    @tool("write_file")
    def write_file(filename: str, content: str) -> str:
        """Write content to a file in the session directory.
        
        Creates parent directories if needed. Use this for creating new files
        or completely replacing existing files.
        
        Args:
            filename: Relative path to the file (e.g., 'public/index.html')
            content: Complete file contents
        
        Returns:
            Success message with byte count, or error message
        """
        if filename.startswith('.'):
            return "Access denied: cannot write system files."
        
        # Add .html extension if no extension provided
        if "." not in Path(filename).name:
            filename = filename + ".html"
        
        try:
            p = _safe(filename)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"✅ Wrote {filename} ({len(content)} bytes)"
        except Exception as e:
            return f"Error writing {filename}: {e}"
    
    @tool("get_business_context")
    def get_business_context() -> str:
        """Get the business context information from Google Places.
        
        Call this to get the client's business data including name, address,
        phone, hours, reviews, photos, and rating.
        
        Returns:
            Formatted business information, or message if not available
        """
        if not biz_ctx:
            return "No business data available for this session."
        
        if "place_data" in biz_ctx:
            return format_business_context(biz_ctx["place_data"])
        elif "formatted" in biz_ctx:
            return biz_ctx["formatted"]
        else:
            return str(biz_ctx)
    
    @tool("get_places_api_docs")
    def get_places_api_docs() -> str:
        """Get documentation for integrating Google Places API in the website.
        
        Returns:
            API integration guide for maps, photos, and place details
        """
        return '''# Google Places API Integration Guide

## Embedding Google Maps

Use the Google Maps JavaScript API to embed a map with the business location:

```html
<div id="map" style="width: 100%; height: 400px;"></div>
<script>
  function initMap() {
    const location = { lat: LATITUDE, lng: LONGITUDE };
    const map = new google.maps.Map(document.getElementById("map"), {
      zoom: 15,
      center: location,
    });
    new google.maps.Marker({ position: location, map: map });
  }
</script>
<script async defer src="https://maps.googleapis.com/maps/api/js?key=YOUR_API_KEY&callback=initMap"></script>
```

## Displaying Photos

Photos from the business context can be displayed using the photo reference:

```html
<img src="https://places.googleapis.com/v1/PHOTO_NAME/media?maxWidthPx=800&key=YOUR_API_KEY" 
     alt="Business photo">
```

## Best Practices

1. Use relative paths for your own assets (css/style.css, not /css/style.css)
2. Make the map responsive with CSS
3. Add loading states for dynamic content
4. Include alt text for accessibility
5. Use the business hours data to show "Open Now" status
'''
    
    return [list_files, read_file, write_file, get_business_context, get_places_api_docs]
