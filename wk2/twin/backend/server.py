from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from typing import Optional, List, Dict
import json
import uuid
from datetime import datetime
from google.cloud import storage
from google.api_core.exceptions import NotFound
from google import genai
from google.genai import types
from google.genai.errors import ClientError
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

# Initialize the Vertex AI client
# On Cloud Run, credentials are picked up automatically from the attached
# service account - no key file or explicit auth needed.
GCP_PROJECT_ID = os.getenv("GCP_PROJECT_ID")
GCP_REGION = os.getenv("GCP_REGION", "us-central1")

genai_client = genai.Client(
    vertexai=True,
    project=GCP_PROJECT_ID,
    location=GCP_REGION,
)

# Gemini model selection
GEMINI_MODEL_ID = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash")

# Memory storage configuration
USE_GCS = os.getenv("USE_GCS", "false").lower() == "true"
GCS_BUCKET = os.getenv("GCS_BUCKET", "")
MEMORY_DIR = os.getenv("MEMORY_DIR", "../memory")

# Initialize Cloud Storage client if needed
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


def call_vertex_ai(conversation: List[Dict], user_message: str) -> str:
    """Call Vertex AI (Gemini) with conversation history"""

    # Gemini uses "model" instead of "assistant" for the AI's turns,
    # and takes the system prompt separately rather than as a message.
    contents = []
    for msg in conversation[-50:]:
        role = "model" if msg["role"] == "assistant" else "user"
        contents.append(
            types.Content(role=role, parts=[types.Part(text=msg["content"])])
        )

    # Add the current user message
    contents.append(
        types.Content(role="user", parts=[types.Part(text=user_message)])
    )

    try:
        response = genai_client.models.generate_content(
            model=GEMINI_MODEL_ID,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=prompt(),
                max_output_tokens=2000,
                temperature=0.7,
                top_p=0.9,
            ),
        )

        return response.text

    except ClientError as e:
        message = str(e)
        if "PERMISSION_DENIED" in message:
            print(f"Vertex AI access denied: {e}")
            raise HTTPException(status_code=403, detail="Access denied to Vertex AI model")
        elif "NOT_FOUND" in message:
            print(f"Vertex AI model not found: {e}")
            raise HTTPException(status_code=400, detail=f"Model not found: {GEMINI_MODEL_ID}")
        else:
            print(f"Vertex AI error: {e}")
            raise HTTPException(status_code=500, detail=f"Vertex AI error: {message}")


@app.get("/")
async def root():
    return {
        "message": "AI Digital Twin API (Powered by Vertex AI)",
        "memory_enabled": True,
        "storage": "GCS" if USE_GCS else "local",
        "ai_model": GEMINI_MODEL_ID
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "use_gcs": USE_GCS,
        "gemini_model": GEMINI_MODEL_ID
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Generate session ID if not provided
        session_id = request.session_id or str(uuid.uuid4())

        # Load conversation history
        conversation = load_conversation(session_id)

        # Call Vertex AI for response
        assistant_response = call_vertex_ai(conversation, request.message)

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

    except HTTPException:
        raise
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