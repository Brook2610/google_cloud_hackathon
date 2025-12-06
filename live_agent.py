"""Gemini Live API handler for voice assistant.

Manages real-time voice conversation with users to gather website requirements.
Uses WebSocket to relay audio between browser and Gemini Live API.
"""
import asyncio
import json
import os
import traceback
from pathlib import Path
from typing import Optional, Callable

from google import genai
from google.genai import types

# Load environment
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / '.env'
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass


# Configuration - Use the working model from gemini_live_voice.py
MODEL = "models/gemini-2.5-flash-native-audio-preview-09-2025"
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000


def get_system_prompt(business_name: Optional[str] = None, place_id: Optional[str] = None) -> str:
    """Build the system prompt for the voice assistant."""
    
    business_context = ""
    if business_name:
        business_context = f"\nThe user has selected their business: {business_name}. Include this in the website description."
    if place_id:
        business_context += f"\nPlace ID: {place_id}"
    
    return f"""You are a friendly Ethiopian website designer assistant. Speak in Amharic (አማርኛ).

Your goal is to gather website requirements by asking MAX 3 questions.

Question flow:
1. Greet warmly (ሰላም!) and ask what type of website they want (business landing page, portfolio, restaurant, etc.)
2. Ask about key features/sections they need (contact form, gallery, menu, about us, etc.)
3. Ask about colors/style preferences (modern, traditional, colorful, minimal, etc.)

Rules:
- Keep questions SHORT and clear
- Listen carefully to their responses
- After 3 questions (or earlier if you have enough info), call the submit_website_description tool
- Be encouraging and friendly
- If they already gave enough info in one answer, you can skip remaining questions
{business_context}

When you have gathered enough information, use the submit_website_description tool with a detailed English description of the website to build. The description should include:
- Type of website
- Key sections and features
- Color scheme and style
- Any specific content mentioned"""


# Tool definition for submitting website description
submit_website_description_decl = {
    "name": "submit_website_description",
    "description": "Submit the final website description to start building. Call this after gathering requirements from the user.",
    "parameters": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Complete description of the website in English, including type, sections, features, colors, and style"
            }
        },
        "required": ["description"]
    }
}


class LiveAssistant:
    """Manages a live voice session with Gemini."""
    
    def __init__(
        self,
        business_name: Optional[str] = None,
        place_id: Optional[str] = None,
        on_audio: Optional[Callable[[bytes], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,
        on_tool_call: Optional[Callable[[str, dict], None]] = None,
        on_end: Optional[Callable[[], None]] = None,
    ):
        self.business_name = business_name
        self.place_id = place_id
        self.on_audio = on_audio
        self.on_transcript = on_transcript
        self.on_tool_call = on_tool_call
        self.on_end = on_end
        
        self.session = None
        self.client = None
        self._running = False
        self._receive_task = None
        self._audio_queue = asyncio.Queue()
        
    async def start(self):
        """Start the live session."""
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY_1")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        
        print(f"🔑 Using API key: {api_key[:10]}...")
        
        # Use v1beta API version like the working example
        self.client = genai.Client(
            http_options={"api_version": "v1beta"},
            api_key=api_key
        )
        
        # Configure session - matching the working example structure
        tools = [types.Tool(function_declarations=[submit_website_description_decl])]
        
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            ),
            tools=tools,
            system_instruction=types.Content(
                parts=[types.Part.from_text(text=get_system_prompt(self.business_name, self.place_id))],
                role="system"
            ),
        )
        
        print(f"🎤 Starting live session with model: {MODEL}")
        print(f"📋 Config: response_modalities={config.response_modalities}")
        
        # Connect using async context manager
        self._session_ctx = self.client.aio.live.connect(model=MODEL, config=config)
        self.session = await self._session_ctx.__aenter__()
        
        self._running = True
        print("✅ Live session connected")
        
        # Start receiving responses in background
        self._receive_task = asyncio.create_task(self._receive_loop())
        print("📡 Receive task started")
        
        # Start audio sending loop
        self._send_task = asyncio.create_task(self._send_audio_loop())
        print("🎙️ Audio send task started")
        
    async def _send_audio_loop(self):
        """Send queued audio to Gemini."""
        print("🎙️ Audio send loop running...")
        while self._running:
            try:
                # Wait for audio with timeout to allow checking _running
                try:
                    audio_data = await asyncio.wait_for(self._audio_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                    
                if audio_data and self.session:
                    await self.session.send_realtime_input(
                        audio=types.Blob(
                            mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                            data=audio_data
                        )
                    )
            except Exception as e:
                print(f"❌ Error in send audio loop: {e}")
        print("🎙️ Audio send loop ended")
        
    async def send_audio(self, audio_data: bytes):
        """Queue audio data to be sent to Gemini."""
        if not self._running:
            return
        await self._audio_queue.put(audio_data)
            
    async def send_text(self, text: str):
        """Send text message to Gemini."""
        if not self.session or not self._running:
            return
            
        try:
            print(f"📝 Sending text: {text[:50]}...")
            await self.session.send_client_content(
                turns={"role": "user", "parts": [{"text": text}]},
                turn_complete=True
            )
        except Exception as e:
            print(f"❌ Error sending text: {e}")
            traceback.print_exc()
            
    async def _receive_loop(self):
        """Receive and process responses from Gemini."""
        print("📡 Starting receive loop...")
        try:
            while self._running:
                print("📡 Waiting for response turn...")
                turn = self.session.receive()
                
                async for response in turn:
                    if not self._running:
                        print("📡 Receive loop: not running, breaking")
                        break
                    
                    print(f"📡 Got response: {type(response).__name__}")
                    
                    # Handle audio data
                    audio_chunks = []
                    
                    sc = getattr(response, "server_content", None)
                    if sc:
                        print(f"  📡 server_content: turn_complete={getattr(sc, 'turn_complete', None)}")
                    
                    model_turn = getattr(sc, "model_turn", None) if sc else None
                    
                    if model_turn:
                        print(f"  📡 model_turn has {len(getattr(model_turn, 'parts', []) or [])} parts")
                        for part in getattr(model_turn, "parts", []) or []:
                            inline = getattr(part, "inline_data", None)
                            if inline and getattr(inline, "data", None):
                                audio_chunks.append(inline.data)
                                print(f"  🔊 Got inline audio: {len(inline.data)} bytes")
                    
                    # Also check direct data field
                    if response.data:
                        audio_chunks.append(response.data)
                        print(f"  🔊 Got direct audio: {len(response.data)} bytes")
                    
                    for chunk in audio_chunks:
                        if chunk and self.on_audio:
                            self.on_audio(chunk)
                    
                    # Handle transcripts
                    if sc and getattr(sc, "output_transcription", None):
                        transcript = sc.output_transcription
                        if getattr(transcript, "text", None):
                            print(f"  💬 Transcript: {transcript.text}")
                            if self.on_transcript:
                                self.on_transcript("assistant", transcript.text)
                        
                    # Handle tool calls
                    if getattr(response, "tool_call", None):
                        tc = response.tool_call
                        print(f"  🔧 Tool call received")
                        
                        # Handle function_calls list
                        if getattr(tc, "function_calls", None):
                            for fc in tc.function_calls:
                                fname = getattr(fc, "name", None)
                                fargs = getattr(fc, "args", {}) or {}
                                
                                if isinstance(fargs, str):
                                    try:
                                        fargs = json.loads(fargs)
                                    except Exception:
                                        pass
                                
                                print(f"  🔧 Tool call: {fname} with args {fargs}")
                                
                                if fname == "submit_website_description":
                                    if self.on_tool_call:
                                        self.on_tool_call(fname, dict(fargs) if fargs else {})
                                    
                                    # Send tool response
                                    await self.session.send_tool_response(
                                        function_responses=[
                                            types.FunctionResponse(
                                                id=getattr(fc, "id", None),
                                                name=fname,
                                                response={"result": "ok", "message": "Website building started"}
                                            )
                                        ]
                                    )
                                    
                                    # End session after tool call
                                    await asyncio.sleep(2)
                                    await self.stop()
                                    return
                
                print("📡 Turn complete, waiting for next turn...")
                            
        except asyncio.CancelledError:
            print("📡 Receive loop cancelled")
        except Exception as e:
            print(f"❌ Receive loop error: {e}")
            traceback.print_exc()
        finally:
            print("📡 Receive loop ended")
            if self.on_end:
                self.on_end()
                
    async def stop(self):
        """Stop the live session."""
        print("🛑 Stopping live session...")
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if hasattr(self, '_send_task') and self._send_task:
            self._send_task.cancel()
            try:
                await self._send_task
            except asyncio.CancelledError:
                pass
        
        if hasattr(self, '_session_ctx') and self._session_ctx:
            try:
                await self._session_ctx.__aexit__(None, None, None)
            except Exception as e:
                print(f"❌ Error closing session: {e}")
                
        print("🛑 Live session stopped")


if __name__ == "__main__":
    async def test():
        assistant = LiveAssistant(
            business_name="Test Coffee Shop",
            on_audio=lambda d: print(f"🔊 Audio: {len(d)} bytes"),
            on_transcript=lambda r, t: print(f"💬 [{r}]: {t}"),
            on_tool_call=lambda n, a: print(f"🔧 Tool: {n}({a})"),
            on_end=lambda: print("🏁 Session ended"),
        )
        await assistant.start()
        await assistant.send_text("I want a modern coffee shop website with a menu section")
        await asyncio.sleep(30)
        await assistant.stop()
    
    asyncio.run(test())
