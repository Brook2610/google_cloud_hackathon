# Google Cloud Hackathon - AI Website Builder

An AI-powered website builder that uses **Gemini 2.0 Flash** and **Gemini Live API** to create professional business websites through voice conversation.

## Features

- 🎙️ **Voice Assistant**: Speak to our AI in Amharic to describe your website
- 🤖 **Intelligent Generation**: AI asks clarifying questions and builds your site
- 📍 **Business Integration**: Search for a business on Google Maps and automatically include its details
- 💬 **Conversational Editing**: Modify your website through natural chat
- 👁️ **Live Preview**: See your website update in real-time
- 📱 **Responsive Design**: All generated sites work on mobile, tablet, and desktop

## Quick Start

### 1. Install Dependencies

```bash
cd google_cloud_hackathon
pip install -r requirements.txt
```

### 2. Configure Environment

Create or update `.env` in the parent directory with:

```env
# Gemini API Key (required for both voice and text generation)
GOOGLE_API_KEY=your_gemini_api_key

# Google Places API Key (optional, for business lookup)
GOOGLE_CLOUD_CREDENTIALS=your_places_api_key
```

### 3. Run the Server

```bash
python api.py
```

Or with uvicorn:

```bash
uvicorn api:app --reload --port 8000
```

### 4. Open in Browser

Navigate to: **http://localhost:8000**

## Usage

### Voice Mode (Initial Build)

1. **Optional**: Search for a business in the Google Places picker
2. **Click "Start Conversation"** to begin voice interaction
3. **Allow microphone access** when prompted
4. **Speak in Amharic** (or English) - AI will ask ~3 questions about your website
5. **Wait** for the AI to build your site automatically
6. **Preview** opens when complete

### Text Mode (Modifications)

After the initial build, you can modify your website through text chat:
- Type changes like "Change the colors to blue and white"
- "Add a contact form"
- "Make the header sticky"

## Project Structure

```
google_cloud_hackathon/
├── api.py              # FastAPI backend with WebSocket support
├── agent.py            # Gemini text agent for website building
├── live_agent.py       # Gemini Live API for voice conversations
├── tools.py            # Agent tools (write_file, read_file, etc.)
├── places.py           # Google Places API integration
├── index.html          # Frontend UI with interactive orb
├── requirements.txt
└── sites/              # Generated websites (created at runtime)
```

## API Endpoints

| Endpoint | Type | Description |
|----------|------|-------------|
| `/` | GET | Serve the UI |
| `/config` | GET | Get API configuration |
| `/session/init` | POST | Initialize new session |
| `/build` | POST | Build a new website (text mode) |
| `/modify` | POST | Modify existing website |
| `/files` | GET | List files in a site |
| `/ws/live` | WebSocket | Live voice conversation |
| `/sites/{id}/...` | GET | Serve generated files |

## Technology Stack

- **Backend**: FastAPI + Python + WebSockets
- **AI**: 
  - Gemini 2.0 Flash (text generation)
  - Gemini Live API (voice conversation)
- **Agent Framework**: LangGraph ReAct Agent
- **Frontend**: Vanilla HTML/CSS/JS with Web Audio API
- **APIs**: Google Places API, Google Maps JavaScript API

## How It Works

### Voice Flow
1. **User clicks Start** → Microphone access requested
2. **WebSocket connection** established to `/ws/live`
3. **Gemini Live API** greets user in Amharic and asks questions
4. **Audio streaming** in both directions (16kHz PCM from browser, 24kHz from Gemini)
5. **Tool calling** - AI calls `submit_website_description` with gathered requirements
6. **Website building** - Text agent generates HTML/CSS/JS files
7. **Transition** to preview mode with text chat

### Text Flow
1. **User types** modification request
2. **Gemini agent** uses tools to read/write files
3. **Live preview** updates automatically

## Dependencies

```
fastapi>=0.109.0          # Web framework
uvicorn[standard]>=0.27.0 # ASGI server
langchain-google-genai>=2.0.0  # Gemini text integration
langgraph>=0.2.0          # Agent framework
python-dotenv>=1.0.0      # Environment variables
google-genai>=0.5.0       # Gemini Live API
```

## License

Built for the Google Cloud Hackathon 2025.
