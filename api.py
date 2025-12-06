"""FastAPI backend for the AI website builder.

Provides REST API endpoints for building and modifying websites using
Gemini AI, with Google Places integration for business context.
"""
import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / '.env'
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

from agent import run_agent, build_website
from places import fetch_place_details, format_business_context
from live_agent import LiveAssistant
from db import save_website, get_website, list_websites

# Configuration
SITES_DIR = Path(__file__).parent / "sites"
SITES_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="Google Cloud Hackathon - Website Builder",
    description="AI-powered website builder using Gemini",
    version="1.0.0",
)


# ============================================================================
# Request/Response Models
# ============================================================================

class BuildRequest(BaseModel):
    spec: str
    site_id: Optional[str] = None
    place_id: Optional[str] = None


class ModifyRequest(BaseModel):
    site_id: str
    instruction: str
    place_id: Optional[str] = None


class SessionInitResponse(BaseModel):
    site_id: str
    message: str


class BuildResponse(BaseModel):
    success: bool
    site_id: str
    files: list
    response: str
    error: Optional[str] = None


# ============================================================================
# Helper Functions
# ============================================================================

def get_site_dir(site_id: str) -> Path:
    """Get the directory for a site, ensuring it exists."""
    site_dir = SITES_DIR / site_id
    site_dir.mkdir(parents=True, exist_ok=True)
    return site_dir


def download_photos_background(place_data: dict, site_dir: Path) -> None:
    """Download photos in background thread.
    
    Args:
        place_data: Place data with photos array
        site_dir: Site directory to save photos to
    """
    if not place_data.get("photos"):
        return
    
    photos_dir = site_dir / "public" / "images"
    photos_dir.mkdir(parents=True, exist_ok=True)
    
    from places import get_api_key, PLACES_BASE
    from urllib import request, parse
    
    try:
        api_key = get_api_key()
    except Exception as e:
        print(f"⚠️ Cannot download photos: {e}")
        return
    
    for i, photo in enumerate(place_data["photos"][:3]):  # Max 3 photos
        photo_name = photo.get("name")
        if not photo_name:
            continue
        
        try:
            media_url = f"{PLACES_BASE}/{parse.quote(photo_name, safe='/')}/media?maxWidthPx=800"
            headers = {"X-Goog-Api-Key": api_key}
            
            req = request.Request(media_url, headers=headers, method="GET")
            out_path = photos_dir / f"photo_{i+1}.jpg"
            
            with request.urlopen(req, timeout=30) as resp, open(out_path, "wb") as f:
                f.write(resp.read())
            
            print(f"📸 Downloaded photo {i+1}: {out_path}")
        except Exception as e:
            print(f"⚠️ Failed to download photo {i+1}: {e}")


def fetch_business_context(place_id: str, site_dir: Path = None) -> Optional[dict]:
    """Fetch business context from Google Places API.
    
    Photos are NOT downloaded here - call start_photo_download() separately
    to download in background while agent runs.
    
    Args:
        place_id: Google Places place ID
        site_dir: Optional site directory (used to determine expected photo paths)
    
    Returns:
        Dictionary with place_data, formatted context, and expected photo paths
    """
    if not place_id:
        return None
    
    try:
        place_data = fetch_place_details(place_id)
        
        # Generate expected local photo paths (photos will be downloaded in background)
        local_photos = []
        if site_dir and place_data.get("photos"):
            for i in range(min(len(place_data["photos"]), 3)):
                local_photos.append(f"images/photo_{i+1}.jpg")
        
        # Add expected local photos to place_data for the AI
        if local_photos:
            place_data["local_photos"] = local_photos
        
        formatted = format_business_context(place_data)
        
        # Tell AI about local photos it should use - make it VERY explicit
        if local_photos:
            formatted += f"\n\n🚨 **CRITICAL: Local Photos Ready to Use in Website**\n"
            formatted += "These photos are downloaded and MUST be included in your HTML:\n"
            for photo_path in local_photos:
                formatted += f"  - `{photo_path}` - Use this EXACT path in <img> tags\n"
            formatted += "\n**Example usage in HTML:**\n"
            formatted += f'  <img src="{local_photos[0]}" alt="Business photo" style="width: 100%; max-width: 800px;">\n'
            if len(local_photos) > 1:
                formatted += f'  <img src="{local_photos[1]}" alt="Business interior">\n'
            formatted += "\n**You MUST include these photos in your website design!**\n"
        
        return {
            "place_id": place_id,
            "place_data": place_data,
            "formatted": formatted,
            "local_photos": local_photos,
        }
    except Exception as e:
        print(f"⚠️ Failed to fetch business context: {e}")
        return None


def create_site_scaffold(site_dir: Path):
    """Create initial site structure with starter files."""
    public = site_dir / "public"
    public.mkdir(exist_ok=True)
    (public / "css").mkdir(exist_ok=True)
    (public / "js").mkdir(exist_ok=True)
    (public / "images").mkdir(exist_ok=True)
    
    # Create starter index.html
    index_path = public / "index.html"
    if not index_path.exists():
        index_path.write_text('''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Building...</title>
    <style>
        body { 
            font-family: system-ui, sans-serif; 
            display: flex; 
            justify-content: center; 
            align-items: center; 
            height: 100vh; 
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        .loading { text-align: center; }
        .spinner { 
            width: 50px; 
            height: 50px; 
            border: 3px solid rgba(255,255,255,0.3);
            border-top: 3px solid white;
            border-radius: 50%; 
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin { 100% { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="loading">
        <div class="spinner"></div>
        <h1>Building your website...</h1>
        <p>This page will be replaced shortly.</p>
    </div>
</body>
</html>
''', encoding='utf-8')


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main voice-based application page."""
    index_path = Path(__file__).parent / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Website Builder</h1><p>index.html not found</p>")


@app.get("/text", response_class=HTMLResponse)
async def text_mode():
    """Serve the text-based application page (backup mode)."""
    index_path = Path(__file__).parent / "index_text.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Website Builder</h1><p>index_text.html not found</p>")


@app.get("/config")
async def get_config():
    """Return configuration for the frontend (Maps API key, etc.)."""
    maps_key = os.getenv("GOOGLE_CLOUD_CREDENTIALS", "")
    return {
        "maps_api_key": maps_key,
        "version": "1.0.0",
    }


@app.post("/session/init", response_model=SessionInitResponse)
async def init_session():
    """Initialize a new site session with scaffold files."""
    site_id = str(uuid.uuid4())[:8]
    site_dir = get_site_dir(site_id)
    create_site_scaffold(site_dir)
    
    return SessionInitResponse(
        site_id=site_id,
        message=f"Session {site_id} initialized"
    )


@app.post("/build", response_model=BuildResponse)
async def build_site(request: BuildRequest):
    """Build a new website based on the specification.
    
    This is a synchronous endpoint - it waits for the build to complete.
    """
    import threading
    
    # Get or create site_id
    site_id = request.site_id or str(uuid.uuid4())[:8]
    site_dir = get_site_dir(site_id)
    
    # Ensure scaffold exists
    create_site_scaffold(site_dir)
    
    # Fetch business context if place_id provided
    biz_ctx = fetch_business_context(request.place_id, site_dir)
    
    # Start photo download in background (runs while agent works)
    if biz_ctx and biz_ctx.get("place_data", {}).get("photos"):
        photo_thread = threading.Thread(
            target=download_photos_background,
            args=(biz_ctx["place_data"], site_dir),
            daemon=True
        )
        photo_thread.start()
        print("📸 Started background photo download...")
    
    print(f"\n🏗️ Building site {site_id}...")
    print(f"📝 Spec: {request.spec[:100]}...")
    if biz_ctx:
        print(f"🏢 Business: {biz_ctx.get('place_data', {}).get('displayName', {}).get('text', 'Unknown')}")
    
    # Run the agent (photos download in parallel)
    result = run_agent(
        session_dir=site_dir,
        user_request=request.spec,
        biz_ctx=biz_ctx,
        max_steps=30,
    )
    
    # Get place name for database
    place_name = None
    if biz_ctx and biz_ctx.get("place_data"):
        place_name = biz_ctx["place_data"].get("displayName", {}).get("text") if isinstance(biz_ctx["place_data"].get("displayName"), dict) else None
    
    # Save to database
    file_count = len(result.get("files", []))
    save_website(
        site_id=site_id,
        description=request.spec,
        place_id=request.place_id,
        place_name=place_name,
        file_count=file_count,
        success=result.get("success", False)
    )
    
    return BuildResponse(
        success=result.get("success", False),
        site_id=site_id,
        files=result.get("files", []),
        response=result.get("response", ""),
        error=result.get("error"),
    )


@app.post("/modify", response_model=BuildResponse)
async def modify_site(request: ModifyRequest):
    """Modify an existing website based on instructions.
    
    This is a synchronous endpoint - it waits for the modification to complete.
    """
    import threading
    
    site_dir = get_site_dir(request.site_id)
    
    if not site_dir.exists():
        raise HTTPException(status_code=404, detail=f"Site {request.site_id} not found")
    
    # Fetch business context if place_id provided
    biz_ctx = fetch_business_context(request.place_id, site_dir)
    
    # Start photo download in background if new photos
    if biz_ctx and biz_ctx.get("place_data", {}).get("photos"):
        photo_thread = threading.Thread(
            target=download_photos_background,
            args=(biz_ctx["place_data"], site_dir),
            daemon=True
        )
        photo_thread.start()
    
    print(f"\n🔧 Modifying site {request.site_id}...")
    print(f"📝 Instruction: {request.instruction[:100]}...")
    
    # Run the agent
    result = run_agent(
        session_dir=site_dir,
        user_request=request.instruction,
        biz_ctx=biz_ctx,
        max_steps=30,
    )
    
    # Update database record
    existing = get_website(request.site_id)
    if existing:
        # Update existing record
        file_count = len(result.get("files", []))
        save_website(
            site_id=request.site_id,
            description=existing.get("description", "") + f"\n\nModified: {request.instruction}",
            place_id=request.place_id or existing.get("place_id"),
            place_name=existing.get("place_name"),
            file_count=file_count,
            success=result.get("success", False)
        )
    
    return BuildResponse(
        success=result.get("success", False),
        site_id=request.site_id,
        files=result.get("files", []),
        response=result.get("response", ""),
        error=result.get("error"),
    )


@app.get("/files")
async def list_files(site_id: str = Query(...)):
    """List files in a site's directory."""
    site_dir = get_site_dir(site_id)
    
    if not site_dir.exists():
        return {"files": []}
    
    files = []
    for f in site_dir.rglob("*"):
        if f.is_file() and not any(part.startswith('.') for part in f.parts):
            files.append(str(f.relative_to(site_dir)))
    
    return {"files": sorted(files)}


@app.get("/websites")
async def list_websites_endpoint(limit: int = Query(50, ge=1, le=100)):
    """List all saved websites.
    
    Args:
        limit: Maximum number of websites to return (1-100)
    
    Returns:
        List of website records
    """
    websites = list_websites(limit=limit)
    return {"websites": websites}


@app.get("/websites/{site_id}")
async def get_website_endpoint(site_id: str):
    """Get a specific website by site_id.
    
    Returns:
        Website record or 404 if not found
    """
    website = get_website(site_id)
    if not website:
        raise HTTPException(status_code=404, detail=f"Website {site_id} not found")
    return website


@app.get("/place/fetch")
async def fetch_place(place_id: str = Query(...)):
    """Fetch business information from Google Places API."""
    try:
        biz_ctx = fetch_business_context(place_id)
        if not biz_ctx:
            raise HTTPException(status_code=404, detail="Place not found or API error")
        return biz_ctx
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WebSocket Live Voice Session - OPTIMIZED for smooth audio
# ============================================================================

@app.websocket("/ws/live")
async def live_voice_session(websocket: WebSocket):
    """WebSocket endpoint for live voice conversation with Gemini.
    
    OPTIMIZED: Uses direct streaming pattern like live/web_voice for smooth audio.
    No intermediate queues or callbacks - direct async streaming.
    
    Protocol:
    - Client sends: {"type": "start", "business_name": "...", "place_id": "..."} to start
    - Client sends: raw PCM bytes for audio (preferred) or {"type": "audio", "data": "<base64>"}
    - Client sends: {"type": "end"} to stop
    
    Server sends:
    - {"type": "audio", "data": "<base64 audio>"} for response audio
    - {"type": "transcript", "role": "assistant", "text": "..."} for transcripts
    - {"type": "interrupted"} when user interrupts
    - {"type": "turn_complete"} when AI finishes speaking
    - {"type": "building", "site_id": "...", "description": "..."} when starting build
    - {"type": "complete", "site_id": "...", "files": [...]} when build is done
    - {"type": "error", "message": "..."} for errors
    """
    await websocket.accept()
    print("🔌 WebSocket connected")
    
    from live_agent import get_client, get_live_config, MODEL, SEND_SAMPLE_RATE
    from google.genai import types
    
    site_id = None
    place_id = None
    session = None
    session_ctx = None
    
    try:
        # Wait for start message
        data = await websocket.receive()
        msg = json.loads(data.get("text", "{}")) if "text" in data else {}
        
        if msg.get("type") != "start":
            await websocket.send_json({"type": "error", "message": "Expected start message"})
            return
        
        business_name = msg.get("business_name")
        place_id = msg.get("place_id")
        
        print(f"🎤 Starting live session. Business: {business_name}")
        
        # Initialize site
        site_id = str(uuid.uuid4())[:8]
        site_dir = get_site_dir(site_id)
        create_site_scaffold(site_dir)
        
        # Connect to Gemini
        client = get_client()
        config = get_live_config(business_name, place_id)
        
        session_ctx = client.aio.live.connect(model=MODEL, config=config)
        session = await session_ctx.__aenter__()
        
        print("✅ Connected to Gemini Live API")
        await websocket.send_json({"type": "started", "site_id": site_id})
        
        # Track if we should stop
        should_stop = False
        
        async def receive_from_client():
            """Receive audio from browser and send directly to Gemini."""
            nonlocal should_stop
            try:
                while not should_stop:
                    data = await websocket.receive()
                    
                    if "bytes" in data and data["bytes"]:
                        # Binary audio - send directly (lowest latency)
                        await session.send_realtime_input(
                            audio=types.Blob(
                                data=data["bytes"],
                                mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                            )
                        )
                    elif "text" in data:
                        msg = json.loads(data["text"])
                        msg_type = msg.get("type", "")
                        
                        if msg_type == "audio":
                            # Base64 audio fallback
                            audio_payload = msg.get("data", "")
                            if audio_payload:
                                audio_data = base64.b64decode(audio_payload)
                                await session.send_realtime_input(
                                    audio=types.Blob(
                                        data=audio_data,
                                        mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}"
                                    )
                                )
                        elif msg_type == "text":
                            # Text message
                            text = msg.get("text", "")
                            if text:
                                await session.send_client_content(
                                    turns={"role": "user", "parts": [{"text": text}]},
                                    turn_complete=True,
                                )
                        elif msg_type == "end":
                            should_stop = True
                            break
                            
            except WebSocketDisconnect:
                should_stop = True
            except Exception as e:
                print(f"❌ Client receive error: {e}")
                should_stop = True
        
        async def receive_from_gemini():
            """Receive responses from Gemini and send to browser."""
            nonlocal should_stop
            try:
                while not should_stop:
                    turn = session.receive()
                    
                    async for response in turn:
                        if should_stop:
                            break
                        
                        # Extract audio chunks
                        audio_chunks = []
                        
                        sc = getattr(response, "server_content", None)
                        model_turn = getattr(sc, "model_turn", None) if sc else None
                        
                        if model_turn:
                            for part in getattr(model_turn, "parts", []) or []:
                                inline = getattr(part, "inline_data", None)
                                if inline and getattr(inline, "data", None):
                                    audio_chunks.append(inline.data)
                        
                        if not audio_chunks and response.data:
                            audio_chunks.append(response.data)
                        
                        # Send audio immediately
                        for chunk in audio_chunks:
                            if chunk:
                                await websocket.send_json({
                                    "type": "audio",
                                    "data": base64.b64encode(chunk).decode("utf-8")
                                })
                        
                        # Send transcription
                        if sc and getattr(sc, "output_transcription", None):
                            transcript = sc.output_transcription
                            if getattr(transcript, "text", None):
                                await websocket.send_json({
                                    "type": "transcript",
                                    "role": "assistant",
                                    "text": transcript.text
                                })
                        
                        # Handle interruption
                        if sc and getattr(sc, "interrupted", None):
                            await websocket.send_json({"type": "interrupted"})
                        
                        # Handle turn complete
                        if sc and getattr(sc, "turn_complete", None):
                            await websocket.send_json({"type": "turn_complete"})
                        
                        # Handle tool calls
                        if getattr(response, "tool_call", None):
                            tc = response.tool_call
                            if getattr(tc, "function_calls", None):
                                for fc in tc.function_calls:
                                    fname = getattr(fc, "name", None)
                                    fargs = getattr(fc, "args", {}) or {}
                                    
                                    if isinstance(fargs, str):
                                        try:
                                            fargs = json.loads(fargs)
                                        except:
                                            pass
                                    
                                    await websocket.send_json({
                                        "type": "tool_call",
                                        "name": fname,
                                        "args": dict(fargs) if fargs else {}
                                    })
                                    
                                    if fname == "submit_website_description":
                                        description = fargs.get("description", "")
                                        
                                        # Send tool response
                                        await session.send_tool_response(
                                            function_responses=[
                                                types.FunctionResponse(
                                                    id=getattr(fc, "id", None),
                                                    name=fname,
                                                    response={"result": "ok", "message": "Website building started"}
                                                )
                                            ]
                                        )
                                        
                                        # Notify client to switch to builder IMMEDIATELY
                                        await websocket.send_json({
                                            "type": "building",
                                            "site_id": site_id,
                                            "description": description
                                        })
                                        
                                        # Signal conversation end to client (after transition)
                                        await websocket.send_json({
                                            "type": "conversation_end"
                                        })
                                        
                                        # Small delay to let final audio play, then close session
                                        await asyncio.sleep(1)
                                        
                                        # Close the Gemini session (conversation is over)
                                        # But keep WebSocket open to send completion later
                                        should_stop = True
                                        
                                        # Close Gemini session explicitly
                                        if session_ctx:
                                            try:
                                                await session_ctx.__aexit__(None, None, None)
                                                session_ctx = None
                                                session = None
                                                print("🔌 Gemini session closed (conversation ended)")
                                            except Exception as e:
                                                print(f"⚠️ Error closing Gemini session: {e}")
                                        
                                        # Fetch business context
                                        biz_ctx = fetch_business_context(place_id, site_dir) if place_id else None
                                        
                                        # Get place name for database
                                        place_name = None
                                        if biz_ctx and biz_ctx.get("place_data"):
                                            place_name = biz_ctx["place_data"].get("displayName", {}).get("text") if isinstance(biz_ctx["place_data"].get("displayName"), dict) else None
                                        
                                        # Start photo download in background
                                        if biz_ctx and biz_ctx.get("place_data", {}).get("photos"):
                                            import threading
                                            photo_thread = threading.Thread(
                                                target=download_photos_background,
                                                args=(biz_ctx["place_data"], site_dir),
                                                daemon=True
                                            )
                                            photo_thread.start()
                                            print("📸 Started background photo download...")
                                        
                                        # Run agent (photos download in parallel)
                                        # Use run_in_executor to prevent blocking the WebSocket loop
                                        loop = asyncio.get_running_loop()
                                        from functools import partial
                                        
                                        result = await loop.run_in_executor(
                                            None,
                                            partial(
                                                run_agent,
                                                session_dir=site_dir,
                                                user_request=description,
                                                biz_ctx=biz_ctx,
                                                max_steps=30,
                                            )
                                        )
                                        
                                        # Save to database
                                        file_count = len(result.get("files", []))
                                        save_website(
                                            site_id=site_id,
                                            description=description,
                                            place_id=place_id,
                                            place_name=place_name,
                                            file_count=file_count,
                                            success=result.get("success", False)
                                        )
                                        
                                        # Send completion
                                        await websocket.send_json({
                                            "type": "complete",
                                            "site_id": site_id,
                                            "files": result.get("files", []),
                                            "success": result.get("success", False),
                                            "response": result.get("response", "")
                                        })
                                        
                                        return
                                        
            except WebSocketDisconnect:
                should_stop = True
            except Exception as e:
                print(f"❌ Gemini receive error: {e}")
                should_stop = True
        
        # Run both tasks concurrently - this is the key for smooth audio!
        async with asyncio.TaskGroup() as tg:
            tg.create_task(receive_from_client())
            tg.create_task(receive_from_gemini())
                
    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        # Only close if not already closed
        if session_ctx:
            try:
                await session_ctx.__aexit__(None, None, None)
            except:
                pass
        print("🔌 WebSocket session closed")


# ============================================================================
# Static File Serving
# ============================================================================

# Mount sites directory for serving generated files
# Access via /sites/{site_id}/public/index.html
app.mount("/sites", StaticFiles(directory=str(SITES_DIR)), name="sites")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("\n🚀 Starting Website Builder API...")
    print(f"📁 Sites directory: {SITES_DIR}")
    print("🌐 Open http://localhost:8000 in your browser\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)
