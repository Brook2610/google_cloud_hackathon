"""Website builder agent using Gemini and LangGraph.

Implements a ReAct agent that uses Gemini to generate websites based on
natural language descriptions and can integrate business data from Google Places.
"""
from pathlib import Path
from typing import Optional
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

from tools import make_website_tools

# Load environment
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / '.env'
    if _env_path.exists():
        load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass


def get_llm():
    """Get the Gemini LLM instance.
    
    Uses gemini-2.5-flash-exp as per the original agent1 configuration.
    """
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY_1")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY not found. Set it in .env or environment."
        )
    
    return ChatGoogleGenerativeAI(
        model="gemini-flash-latest",
        google_api_key=api_key,
        temperature=0.3,
        streaming=True,
    )


def build_system_prompt(session_dir: Path, biz_ctx: dict = None) -> str:
    """Build the system prompt for the website builder agent.
    
    Args:
        session_dir: Session directory for context
        biz_ctx: Optional business context
    
    Returns:
        Complete system prompt string
    """
    # Build repo tree
    repo_tree = ""
    try:
        files = []
        for f in session_dir.rglob("*"):
            if f.is_file() and not any(part.startswith('.') for part in f.parts):
                files.append(str(f.relative_to(session_dir)))
        if files:
            repo_tree = "\n".join(f"  - {f}" for f in sorted(files)[:50])
        else:
            repo_tree = "(empty project)"
    except Exception:
        repo_tree = "(unable to read)"
    
    # Business data note
    business_note = ""
    if biz_ctx and biz_ctx.get("place_data"):
        local_photos = biz_ctx.get("local_photos", [])
        photos_note = ""
        if local_photos:
            photos_note = f"""
**IMPORTANT - Local Photos Available:**
The following photos have been downloaded and are ready to use in your HTML:
{chr(10).join(f"  - `{photo}`" for photo in local_photos)}

**You MUST use these photos in the website!** Include them in:
- Hero/banner sections
- Gallery sections  
- About/feature sections
- Anywhere images would enhance the design

Use them like: `<img src="{local_photos[0] if local_photos else 'images/photo_1.jpg'}" alt="Business photo">`
"""
        
        business_note = f"""
✅ **Business data is available!** Call `get_business_context()` to access:
- Business name, address, phone
- Opening hours
- Customer reviews and ratings
- Photos (local files ready to use)
- Google Maps location

{photos_note}
"""
    else:
        business_note = """
ℹ️ No business data available. Work with the client's request only.
"""

    return f'''# Website Builder Agent

You are an expert web developer that creates complete, production-ready websites using HTML, CSS, and JavaScript.

## Your Role
Build beautiful, functional websites quickly and efficiently. You have tools for file operations and business data integration.

## Core Principles
1. **Complete Implementation**: Create full, working files - no placeholders or TODOs
2. **Efficiency First**: Minimize steps - create complete files in one go
3. **Responsive Design**: All websites must work on mobile, tablet, and desktop
4. **Accessibility**: Use semantic HTML and proper ARIA labels

## Available Tools
- `list_files()` - See what files exist
- `read_file(filename)` - Read a file's contents
- `write_file(filename, content)` - Create or overwrite a file
- `get_business_context()` - Get client's business data (if available)
- `get_places_api_docs()` - Get Google Places integration guide

## Workflow
1. **Understand**: Read the user's request carefully
2. **Plan**: Decide what files to create (HTML, CSS, JS)
3. **Get Business Data**: If business data available, ALWAYS call `get_business_context()` first
4. **Implement**: Create complete files using `write_file` - INCLUDE PHOTOS if available
5. **Integrate**: Use all business data including photos, address, hours, reviews
6. **Finish**: Provide a brief summary and STOP

## Critical Rules
✅ **DO**:
- Use `write_file(filename, content)` to create files
- Create complete files with full content in one step
- **ALWAYS call `get_business_context()` if business data is available**
- **ALWAYS include photos in the website if local photos are mentioned**
- Integrate real business data when available (name, address, phone, hours, reviews, photos)
- Write responsive CSS with mobile-first approach
- Use relative paths for assets (e.g., `css/style.css`, NOT `/css/style.css`)
- Use relative paths for images (e.g., `images/photo_1.jpg`, NOT `/images/photo_1.jpg`)
- Provide a brief summary when done

❌ **DON'T**:
- Leave placeholder comments like "// Add more here"
- Read files back after creating them (waste of steps)
- Create empty or incomplete files
- Use absolute paths (they break proxy URLs)

## Asset Paths (CRITICAL)
Always use relative paths:
- ✅ `<link rel="stylesheet" href="css/style.css">`
- ✅ `<script src="js/main.js"></script>`
- ❌ `href="/css/style.css"` (absolute paths break proxy URLs)

## Design Guidelines
- Modern, clean design with good spacing
- Professional color schemes
- Smooth transitions and hover effects
- CSS Grid/Flexbox for layouts
- Proper typography hierarchy

## Business Data
{business_note}

## Current Project Structure
```
{repo_tree}
```

Use the existing `public/` directory for your files.

## Completion
When finished, provide a brief summary like:
"Created a [description] website with [features]. The site includes [key sections] and is fully responsive."

Then STOP. Do not continue with unnecessary verification steps.
'''


def run_agent(
    session_dir: Path,
    user_request: str,
    biz_ctx: dict = None,
    max_steps: int = 30,
) -> dict:
    """Run the website builder agent.
    
    Args:
        session_dir: Directory for session files
        user_request: User's request for the website
        biz_ctx: Optional business context
        max_steps: Maximum agent steps (default: 30)
    
    Returns:
        Dictionary with results including changed files and final response
    """
    print(f"\n{'='*50}")
    print("🚀 Website Builder Agent")
    print(f"{'='*50}")
    print(f"Request: {user_request[:100]}...")
    
    # Ensure session directory exists with structure
    session_dir = Path(session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Get LLM and tools
    llm = get_llm()
    tools = make_website_tools(session_dir, biz_ctx)
    
    # Build system prompt
    system_prompt = build_system_prompt(session_dir, biz_ctx)
    
    # Create agent with prompt parameter (updated LangGraph API)
    agent = create_react_agent(
        llm,
        tools,
        prompt=system_prompt,  # Use 'prompt' instead of 'state_modifier'
    )
    
    # Run agent
    print("\n🔧 Starting agent execution...")
    
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=user_request)]},
            {"recursion_limit": max_steps},
        )
        
        # Extract final response
        messages = result.get("messages", [])
        final_response = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.content:
                content = msg.content
                if isinstance(content, str) and len(content) > 10:
                    # Skip tool outputs
                    if not content.startswith("✅ Wrote") and not content.startswith("File not found"):
                        final_response = content
                        break
        
        # List changed files
        changed_files = []
        for f in session_dir.rglob("*"):
            if f.is_file() and not any(part.startswith('.') for part in f.parts):
                changed_files.append(str(f.relative_to(session_dir)))
        
        print(f"\n✅ Agent complete! Created {len(changed_files)} files.")
        
        return {
            "success": True,
            "files": sorted(changed_files),
            "response": final_response,
            "messages": messages,
        }
        
    except Exception as e:
        print(f"\n❌ Agent error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "files": [],
            "response": f"Error: {e}",
        }


def build_website(
    site_dir: Path,
    site_id: str,
    spec: str,
    biz_ctx: dict = None,
    max_steps: int = 30,
) -> dict:
    """Convenience wrapper for building a website.
    
    Args:
        site_dir: Site directory
        site_id: Site identifier
        spec: User specification
        biz_ctx: Business context
        max_steps: Maximum agent steps
    
    Returns:
        Build result dictionary
    """
    return run_agent(
        session_dir=site_dir,
        user_request=spec,
        biz_ctx=biz_ctx,
        max_steps=max_steps,
    )
