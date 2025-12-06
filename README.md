# Google Cloud Hackathon - AI Website Builder

An AI-powered website builder that uses **Gemini 2.0 Flash** and **Google Places API** to create professional business websites instantly.

## Features

- 🤖 **Intelligent Generation**: Describe your website in natural language, AI builds it
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
# Gemini API Key (required)
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

1. **Optional**: Search for a business in the Google Places picker
2. **Describe** the website you want (e.g., "Create a modern landing page for my coffee shop")
3. **Wait** for the AI to build your site
4. **Modify** by chatting (e.g., "Change the colors to blue and white")

## Project Structure

```
google_cloud_hackathon/
├── api.py          # FastAPI backend
├── agent.py        # Gemini AI agent
├── tools.py        # Agent tools (write_file, read_file, etc.)
├── places.py       # Google Places API integration
├── index.html      # Frontend UI
├── requirements.txt
└── sites/          # Generated websites (created at runtime)
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Serve the UI |
| `/config` | GET | Get API configuration |
| `/session/init` | POST | Initialize new session |
| `/build` | POST | Build a new website |
| `/modify` | POST | Modify existing website |
| `/files` | GET | List files in a site |
| `/sites/{id}/...` | GET | Serve generated files |

## Technology Stack

- **Backend**: FastAPI + Python
- **AI**: Gemini 2.5 Flash via LangChain
- **Agent Framework**: LangGraph ReAct Agent
- **Frontend**: Vanilla HTML/CSS/JS
- **APIs**: Google Places API, Google Maps JavaScript API

## How It Works

1. **User Input**: User describes the website or selects a Google Business Profile
2. **Context Gathering**: If a business is selected, fetch details from Google Places API
3. **AI Generation**: Gemini agent uses tools to create HTML, CSS, and JavaScript files
4. **Live Preview**: Generated files are served through FastAPI and displayed in an iframe
5. **Iterative Refinement**: User can request changes through natural language chat

## License

Built for the Google Cloud Hackathon 2025.
