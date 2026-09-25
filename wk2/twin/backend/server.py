from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI
import os
from dotenv import load_dotenv
from typing import Optional, List, Dict
import json
import uuid
from datetime import datetime
from google.cloud import storage
from google.api_core.exceptions import NotFound
from context import prompt

# Load environment variables
load_dotenv()

app = FastAPI()

# Configure CORS
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Initialize OpenAI client
openai_kwargs = {"api_key": os.getenv("OPENAI_API_KEY")}
if os.getenv("OPENAI_BASE_URL"):
    openai_kwargs["base_url"] = os.getenv("OPENAI_BASE_URL")
client = OpenAI(**openai_kwargs)

# Memory storage configuration
USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
MEMORY_DIR = os.getenv("MEMORY_DIR", "../memory")

# Initialize Cloud Storage client if needed
# On Cloud Run, credentials are picked up automatically from the
# attached service account — no key file or explicit auth needed.
if USE_GCS:
    storage_client = storage.Client()
    bucket = storage_client.bucket(GCS_BUCKET)


# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class Message(BaseModel):
    role: str
    content: str
    timestamp: str


# Memory management functions
def get_memory_path(session_id: str) -> str:
    return f"{session_id}.json"


def load_conversation(session_id: str) -> List[Dict]:
    """Load conversation history from storage"""
    if USE_GCS:
        blob = bucket.blob(get_memory_path(session_id))
        try:
            return json.loads(blob.download_as_text())
        except NotFound:
            return []
    else:
        # Local file storage
        file_path = os.path.join(MEMORY_DIR, get_memory_path(session_id))
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                return json.load(f)
        return []


def save_conversation(session_id: str, messages: List[Dict]):
    """Save conversation history to storage"""
    if USE_GCS:
        blob = bucket.blob(get_memory_path(session_id))
        blob.upload_from_string(
            json.dumps(messages, indent=2),
            content_type="application/json",
        )
    else:
        # Local file storage
        os.makedirs(MEMORY_DIR, exist_ok=True)
        file_path = os.path.join(MEMORY_DIR, get_memory_path(session_id))
        with open(file_path, "w") as f:
            json.dump(messages, f, indent=2)


@app.get("/")
async def root():
    return {
        "message": "AI Digital Twin API",
        "memory_enabled": True,
        "storage": "GCS" if USE_GCS else "local",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy", "use_gcs": USE_GCS}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Load conversation history
        conversation = load_conversation(session_id)

        # Build messages for OpenAI
        messages = [{"role": "system", "content": prompt()}]

        # Add conversation history (keep last 10 messages for context window)
        for msg in conversation[-10:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Add current user message
        messages.append({"role": "user", "content": request.message})

        # Call OpenAI API
        model_name = os.getenv("OPENAI_MODEL", "gemini-3.6-flash")
        response = client.chat.completions.create(
            model=model_name,
            messages=messages
        )

        assistant_response = response.choices[0].message.content

        # Update conversation history
        conversation.append(
            {"role": "user", "content": request.message, "timestamp": datetime.now().isoformat()}
        )
        conversation.append(
            {
                "role": "assistant",
                "content": assistant_response,
                "timestamp": datetime.now().isoformat(),
            }
        )

        # Save conversation
        save_conversation(session_id, conversation)

        return ChatResponse(response=assistant_response, session_id=session_id)

    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    """Retrieve conversation history"""
    try:
        conversation = load_conversation(session_id)
        return {"session_id": session_id, "messages": conversation}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
