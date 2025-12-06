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


def fetch_business_context(place_id: str) -> Optional[dict]:
    """Fetch business context from Google Places API.
    
    Args:
        place_id: Google Places place ID
    
    Returns:
        Dictionary with place_data and formatted context, or None on error
    """
    if not place_id:
        return None
    
    try:
        place_data = fetch_place_details(place_id)
        formatted = format_business_context(place_data)
        return {
            "place_id": place_id,
            "place_data": place_data,
            "formatted": formatted,
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
    # Get or create site_id
    site_id = request.site_id or str(uuid.uuid4())[:8]
    site_dir = get_site_dir(site_id)
    
    # Ensure scaffold exists
    create_site_scaffold(site_dir)
    
    # Fetch business context if place_id provided
    biz_ctx = fetch_business_context(request.place_id)
    
    print(f"\n🏗️ Building site {site_id}...")
    print(f"📝 Spec: {request.spec[:100]}...")
    if biz_ctx:
        print(f"🏢 Business: {biz_ctx.get('place_data', {}).get('displayName', {}).get('text', 'Unknown')}")
    
    # Run the agent
    result = run_agent(
        session_dir=site_dir,
        user_request=request.spec,
        biz_ctx=biz_ctx,
        max_steps=30,
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
    site_dir = get_site_dir(request.site_id)
    
    if not site_dir.exists():
        raise HTTPException(status_code=404, detail=f"Site {request.site_id} not found")
    
    # Fetch business context if place_id provided
    biz_ctx = fetch_business_context(request.place_id)
    
    print(f"\n🔧 Modifying site {request.site_id}...")
    print(f"📝 Instruction: {request.instruction[:100]}...")
    
    # Run the agent
    result = run_agent(
        session_dir=site_dir,
        user_request=request.instruction,
        biz_ctx=biz_ctx,
        max_steps=30,
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


@app.get("/sites/{site_id}/{path:path}")
async def serve_site_file(site_id: str, path: str):
    """Serve files from generated sites for preview."""
    site_dir = get_site_dir(site_id)
    file_path = site_dir / path
    
    # Security: ensure path doesn't escape site directory
    try:
        file_path.resolve().relative_to(site_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    
    if not file_path.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    
    # Determine content type
    suffix = file_path.suffix.lower()
    content_types = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
    }
    media_type = content_types.get(suffix, "application/octet-stream")
    
    return FileResponse(file_path, media_type=media_type)


# ============================================================================
# WebSocket Live Voice Session
# ============================================================================

@app.websocket("/ws/live")
async def live_voice_session(websocket: WebSocket):
    """WebSocket endpoint for live voice conversation with Gemini.
    
    Protocol:
    - Client sends: {"type": "start", "business_name": "...", "place_id": "..."} to start
    - Client sends: {"type": "audio", "data": "<base64 audio>"} for audio chunks
    - Client sends: {"type": "end"} to stop
    
    Server sends:
    - {"type": "audio", "data": "<base64 audio>"} for response audio
    - {"type": "transcript", "role": "assistant", "text": "..."} for transcripts
    - {"type": "tool_call", "name": "submit_website_description", "args": {...}}
    - {"type": "building", "site_id": "...", "description": "..."} when starting build
    - {"type": "complete", "site_id": "...", "files": [...]} when build is done
    - {"type": "error", "message": "..."} for errors
    """
    await websocket.accept()
    print("🔌 WebSocket connected")
    
    assistant = None
    site_id = None
    place_id = None
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            msg = json.loads(data)
            msg_type = msg.get("type", "")
            
            if msg_type == "start":
                # Start live session
                business_name = msg.get("business_name")
                place_id = msg.get("place_id")
                
                print(f"🎤 Starting live session. Business: {business_name}")
                
                # Initialize site
                site_id = str(uuid.uuid4())[:8]
                site_dir = get_site_dir(site_id)
                create_site_scaffold(site_dir)
                
                # Create assistant with callbacks
                async def send_audio(audio_data: bytes):
                    try:
                        await websocket.send_json({
                            "type": "audio",
                            "data": base64.b64encode(audio_data).decode("utf-8")
                        })
                    except Exception as e:
                        print(f"Error sending audio: {e}")
                
                async def send_transcript(role: str, text: str):
                    try:
                        await websocket.send_json({
                            "type": "transcript",
                            "role": role,
                            "text": text
                        })
                    except Exception as e:
                        print(f"Error sending transcript: {e}")
                
                async def handle_tool_call(name: str, args: dict):
                    try:
                        await websocket.send_json({
                            "type": "tool_call",
                            "name": name,
                            "args": args
                        })
                        
                        if name == "submit_website_description":
                            description = args.get("description", "")
                            
                            # Notify client we're starting build
                            await websocket.send_json({
                                "type": "building",
                                "site_id": site_id,
                                "description": description
                            })
                            
                            # Fetch business context if we have place_id
                            biz_ctx = fetch_business_context(place_id) if place_id else None
                            
                            # Run the website builder agent
                            result = run_agent(
                                session_dir=site_dir,
                                user_request=description,
                                biz_ctx=biz_ctx,
                                max_steps=30,
                            )
                            
                            # Send completion
                            await websocket.send_json({
                                "type": "complete",
                                "site_id": site_id,
                                "files": result.get("files", []),
                                "success": result.get("success", False),
                                "response": result.get("response", "")
                            })
                    except Exception as e:
                        print(f"Error handling tool call: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": str(e)
                        })
                
                def on_audio_sync(audio_data: bytes):
                    asyncio.create_task(send_audio(audio_data))
                
                def on_transcript_sync(role: str, text: str):
                    asyncio.create_task(send_transcript(role, text))
                
                def on_tool_call_sync(name: str, args: dict):
                    asyncio.create_task(handle_tool_call(name, args))
                
                def on_end():
                    print("🛑 Live session ended")
                
                assistant = LiveAssistant(
                    business_name=business_name,
                    place_id=place_id,
                    on_audio=on_audio_sync,
                    on_transcript=on_transcript_sync,
                    on_tool_call=on_tool_call_sync,
                    on_end=on_end,
                )
                
                await assistant.start()
                
                await websocket.send_json({
                    "type": "started",
                    "site_id": site_id
                })
                
            elif msg_type == "audio":
                # Relay audio to Gemini
                if assistant:
                    audio_data = base64.b64decode(msg.get("data", ""))
                    await assistant.send_audio(audio_data)
                    
            elif msg_type == "text":
                # Send text message to Gemini
                if assistant:
                    await assistant.send_text(msg.get("text", ""))
                    
            elif msg_type == "end":
                # End session
                if assistant:
                    await assistant.stop()
                break
                
    except WebSocketDisconnect:
        print("🔌 WebSocket disconnected")
    except Exception as e:
        print(f"❌ WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass
    finally:
        if assistant:
            await assistant.stop()


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
