"""Gemini Live API handler for voice assistant.

Manages real-time voice conversation with users to gather website requirements.
Uses WebSocket to relay audio between browser and Gemini Live API.
"""
import asyncio
import base64
import json
import os
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


# Configuration
MODEL = "gemini-2.5-flash-live-001"
AUDIO_SAMPLE_RATE = 24000  # Gemini outputs 24kHz audio


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
SUBMIT_WEBSITE_DESCRIPTION_TOOL = {
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
        self._session_context = None
        self._receive_task = None
        
    async def start(self):
        """Start the live session."""
        api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY_1")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY not set")
        
        self.client = genai.Client(api_key=api_key)
        
        # Configure session
        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=types.Content(
                parts=[types.Part(text=get_system_prompt(self.business_name, self.place_id))]
            ),
            tools=[types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="submit_website_description",
                    description="Submit the final website description to start building.",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "description": types.Schema(
                                type="STRING",
                                description="Complete description of the website"
                            )
                        },
                        required=["description"]
                    )
                )
            ])],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Aoede")
                )
            )
        )
        
        print(f"🎤 Starting live session with model: {MODEL}")
        
        # Use async context manager properly
        self._session_context = self.client.aio.live.connect(model=MODEL, config=config)
        self.session = await self._session_context.__aenter__()
        
        self._running = True
        print("✅ Live session connected")
        
        # Start receiving responses in background
        self._receive_task = asyncio.create_task(self._receive_loop())
        
    async def send_audio(self, audio_data: bytes):
        """Send audio data to Gemini."""
        if not self.session or not self._running:
            return
            
        try:
            await self.session.send_realtime_input(
                audio=types.Blob(
                    mime_type="audio/pcm;rate=16000",
                    data=audio_data
                )
            )
        except Exception as e:
            print(f"❌ Error sending audio: {e}")
            
    async def send_text(self, text: str):
        """Send text message to Gemini."""
        if not self.session or not self._running:
            return
            
        try:
            await self.session.send_client_content(
                turns=types.Content(parts=[types.Part(text=text)])
            )
        except Exception as e:
            print(f"❌ Error sending text: {e}")
            
    async def _receive_loop(self):
        """Receive and process responses from Gemini."""
        try:
            async for response in self.session.receive():
                if not self._running:
                    break
                    
                # Handle audio data
                if response.data is not None:
                    if self.on_audio:
                        self.on_audio(response.data)
                        
                # Handle server content (transcripts)
                if response.server_content:
                    content = response.server_content
                    
                    # Check for model turn (AI speaking)
                    if hasattr(content, 'model_turn') and content.model_turn:
                        for part in content.model_turn.parts or []:
                            if hasattr(part, 'text') and part.text:
                                if self.on_transcript:
                                    self.on_transcript("assistant", part.text)
                        
                # Handle tool calls
                if response.tool_call:
                    for fc in response.tool_call.function_calls or []:
                        print(f"🔧 Tool call: {fc.name}")
                        
                        if fc.name == "submit_website_description":
                            args = {}
                            if hasattr(fc, 'args'):
                                args = dict(fc.args) if fc.args else {}
                            
                            if self.on_tool_call:
                                self.on_tool_call(fc.name, args)
                                
                            # Send tool response
                            await self.session.send_tool_response(
                                function_responses=[
                                    types.FunctionResponse(
                                        id=fc.id,
                                        name=fc.name,
                                        response={"result": "ok", "message": "Website building started"}
                                    )
                                ]
                            )
                            
                            # End session after tool call
                            await asyncio.sleep(2)
                            await self.stop()
                            return
                            
        except Exception as e:
            print(f"❌ Receive loop error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            if self.on_end:
                self.on_end()
                
    async def stop(self):
        """Stop the live session."""
        self._running = False
        
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception:
                pass
                
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
