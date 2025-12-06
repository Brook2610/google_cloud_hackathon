"""Google Places API integration for business context.

Provides functions to fetch business information from Google Places API
and format it for use in website generation.
"""
import os
import json
import datetime as _dt
from urllib import request, parse, error
from typing import Optional, Dict, Any
from pathlib import Path

# Load .env from base directory
try:
    from dotenv import load_dotenv
    # Load from parent directory (base directory pattern)
    _env_path = Path(__file__).resolve().parents[1] / '.env'
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

PLACES_BASE = "https://places.googleapis.com/v1"


def get_api_key() -> str:
    """Get the Google Cloud API key from environment."""
    key = os.environ.get("GOOGLE_CLOUD_CREDENTIALS")
    if not key:
        raise RuntimeError(
            "GOOGLE_CLOUD_CREDENTIALS not found in environment. "
            "Ensure .env exists in base directory or set the env var."
        )
    return key


def _http_get(url: str, headers: Dict[str, str]) -> bytes:
    """Make an HTTP GET request."""
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace") if hasattr(e, 'read') else str(e)
        raise RuntimeError(f"HTTP {e.code} for {url}: {msg}") from e
    except error.URLError as e:
        raise RuntimeError(f"Network error for {url}: {e}") from e


def fetch_place_details(
    place_id: str,
    field_mask: str = "id,displayName,formattedAddress,nationalPhoneNumber,websiteUri,regularOpeningHours,reviews,photos,rating,userRatingCount,types,googleMapsUri",
    api_key: Optional[str] = None,
    language_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch Place Details (New) for a place_id with a field mask.
    
    Args:
        place_id: Google Places place ID
        field_mask: Comma-separated list of fields to return
        api_key: Optional API key (uses env if not provided)
        language_code: Optional language code (e.g., 'en')
    
    Returns:
        Dictionary with place details
    """
    api_key = api_key or get_api_key()
    
    # Build URL with optional query params
    base = f"{PLACES_BASE}/places/{parse.quote(place_id)}"
    qs = {}
    if language_code:
        qs["languageCode"] = language_code
    url = base + ("?" + parse.urlencode(qs) if qs else "")
    
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": field_mask,
        "Content-Type": "application/json",
    }
    
    raw = _http_get(url, headers)
    return json.loads(raw.decode("utf-8"))


def filter_reviews(
    data: Dict[str, Any],
    min_rating: Optional[int] = None,
    since: Optional[_dt.datetime] = None,
    top: Optional[int] = None,
    sort_newest_first: bool = True,
) -> Dict[str, Any]:
    """Return a shallow copy of data with reviews filtered/sorted locally.
    
    Args:
        data: Place details dictionary
        min_rating: Minimum star rating (1-5)
        since: Only include reviews after this date
        top: Maximum number of reviews to return
        sort_newest_first: Sort by date descending
    
    Returns:
        Filtered place details dictionary
    """
    result = dict(data)
    reviews = list(result.get("reviews", []) or [])

    # Filter by min_rating
    if min_rating is not None:
        reviews = [r for r in reviews if int(r.get("rating", 0)) >= min_rating]

    # Filter by since date
    if since is not None:
        def _parse_dt(s: str) -> Optional[_dt.datetime]:
            try:
                return _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except Exception:
                return None
        reviews = [r for r in reviews if (dt := _parse_dt(r.get("publishTime", ""))) and dt >= since]

    # Sort by publishTime
    if sort_newest_first:
        def _key(r):
            try:
                return _dt.datetime.fromisoformat(r.get("publishTime", "").replace("Z", "+00:00"))
            except Exception:
                return _dt.datetime.min
        reviews.sort(key=_key, reverse=True)

    # Top N
    if top is not None and top > 0:
        reviews = reviews[:top]

    result["reviews"] = reviews
    return result


def download_first_photo(
    place_id: str,
    api_key: Optional[str] = None,
    max_width: Optional[int] = None,
    max_height: Optional[int] = None,
    out_path: str = "place_photo.jpg",
) -> str:
    """Get first photo from Place Details and download via Photos media endpoint.
    
    Args:
        place_id: Google Places place ID
        api_key: Optional API key
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels
        out_path: Output file path
    
    Returns:
        Path to downloaded photo
    """
    api_key = api_key or get_api_key()
    details = fetch_place_details(place_id, field_mask="photos", api_key=api_key)
    photos = details.get("photos") or []
    if not photos:
        raise RuntimeError("No photos available for this place.")
    photo_name = photos[0].get("name")
    if not photo_name:
        raise RuntimeError("Photo name missing in photos[0].")

    # Build media URL
    qs = {}
    if max_width:
        qs["maxWidthPx"] = str(max_width)
    if max_height:
        qs["maxHeightPx"] = str(max_height)
    qstr = ("?" + parse.urlencode(qs)) if qs else ""
    media_url = f"{PLACES_BASE}/{parse.quote(photo_name, safe='/')}/media{qstr}"
    headers = {"X-Goog-Api-Key": api_key}

    # Download binary
    req = request.Request(media_url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=60) as resp, open(out_path, "wb") as f:
            f.write(resp.read())
    except error.HTTPError as e:
        msg = e.read().decode("utf-8", errors="replace") if hasattr(e, 'read') else str(e)
        raise RuntimeError(f"Photo download failed: HTTP {e.code}: {msg}") from e
    except error.URLError as e:
        raise RuntimeError(f"Photo download network error: {e}") from e

    return out_path


def format_business_context(place_data: Dict[str, Any]) -> str:
    """Format place data into a readable context string for the LLM.
    
    Args:
        place_data: Place details from fetch_place_details()
    
    Returns:
        Formatted string with business information
    """
    lines = ["## Business Information\n"]
    
    # Basic info
    if name := place_data.get("displayName", {}).get("text"):
        lines.append(f"**Name:** {name}")
    if addr := place_data.get("formattedAddress"):
        lines.append(f"**Address:** {addr}")
    if phone := place_data.get("nationalPhoneNumber"):
        lines.append(f"**Phone:** {phone}")
    if website := place_data.get("websiteUri"):
        lines.append(f"**Website:** {website}")
    if rating := place_data.get("rating"):
        count = place_data.get("userRatingCount", 0)
        lines.append(f"**Rating:** {rating}/5 ({count} reviews)")
    if maps_uri := place_data.get("googleMapsUri"):
        lines.append(f"**Google Maps:** {maps_uri}")
    
    # Business types
    if types := place_data.get("types"):
        formatted_types = [t.replace("_", " ").title() for t in types[:5]]
        lines.append(f"**Type:** {', '.join(formatted_types)}")
    
    # Opening hours
    if hours := place_data.get("regularOpeningHours"):
        if weekday := hours.get("weekdayDescriptions"):
            lines.append("\n**Hours:**")
            for day in weekday:
                lines.append(f"  - {day}")
    
    # Reviews
    if reviews := place_data.get("reviews"):
        lines.append(f"\n**Reviews ({len(reviews)} shown):**")
        for i, review in enumerate(reviews[:5], 1):
            author = review.get("authorAttribution", {}).get("displayName", "Anonymous")
            rating = review.get("rating", "?")
            text = review.get("text", {}).get("text", "")[:200]
            if text:
                lines.append(f"\n  {i}. **{author}** ({rating}★): \"{text}...\"" if len(text) == 200 else f"\n  {i}. **{author}** ({rating}★): \"{text}\"")
    
    # Photos
    if photos := place_data.get("photos"):
        lines.append(f"\n**Photos:** {len(photos)} available")
        for i, photo in enumerate(photos[:3], 1):
            if name := photo.get("name"):
                lines.append(f"  - Photo {i}: {name}")
    
    return "\n".join(lines)
