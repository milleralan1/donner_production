# Day 3: Transition to Vertex AI

## From OpenAI to Google Cloud AI Services

Welcome to Day 3! Today, we're making a significant architectural shift - replacing OpenAI with **Vertex AI** for AI responses. This change brings several advantages: lower latency (requests stay within GCP), potential cost savings, and deeper integration with the rest of your Google Cloud infrastructure. You'll learn how enterprise applications leverage cloud-native AI services for production deployments.

## What You'll Learn Today

- **Vertex AI fundamentals** - Google's managed generative AI service
- **Gemini models** - Google's latest foundation models
- **IAM permissions for AI services** - Security best practices
- **Model selection** based on cost and performance
- **Cloud Monitoring & Logging** for AI applications
- **Production AI deployment patterns** in GCP

## Understanding Vertex AI

### What is Vertex AI?

Vertex AI is Google Cloud's fully managed platform for machine learning and generative AI, giving you access to Google's Gemini models (plus a curated set of third-party and open models) through a single API. Key benefits include:

- **No infrastructure management** - Fully managed model serving
- **Pay per request** - No upfront costs or idle charges
- **Low latency** - Models run in (or near) your GCP region
- **Enterprise security** - IAM integration, VPC Service Controls, encryption at rest and in transit
- **Multiple model choices** - Gemini, Gemma, and partner/open models via Model Garden

### Gemini Models

Google's Gemini family of models offers different tiers optimized for different use cases:

- **Gemini Flash-Lite** - Fastest, most cost-effective for simple tasks
- **Gemini Flash** - Balanced performance for general use
- **Gemini Pro** - Highest capability for complex reasoning

Today, we'll implement all three so you can choose based on your needs. (Check the [Vertex AI model list](https://cloud.google.com/vertex-ai/generative-ai/docs/models) for the exact current model IDs, since Google periodically ships new point releases.)

## Part 1: Configure IAM Permissions

Unlike the AWS version, there's no root-vs-IAM-user dance here — you simply grant the `twin-runtime` service account (created on Day 2) an additional role, and enable the Vertex AI API.

### Step 1: Enable the Vertex AI API

```bash
gcloud services enable aiplatform.googleapis.com
```

### Step 2: Grant the Service Account Access to Vertex AI

```bash
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:twin-runtime@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

Your `twin-runtime` service account now has:
- `roles/storage.objectAdmin` (from Day 2 — for conversation memory)
- `roles/aiplatform.user` (new! — for calling Gemini via Vertex AI)

That's the entire IAM setup — no separate group, no policy-attachment dance, and nothing to remove and re-add.

## Part 2: Model Access and Quotas

**Good news: unlike some providers, you generally don't need to request access to Gemini models on Vertex AI** — GA (generally available) Gemini models are available to any project with the Vertex AI API enabled and billing configured.

A few things worth knowing:

1. **Regional availability**: most Gemini models are available in multiple regions (e.g., `us-central1`, `europe-west4`) and also via a `global` endpoint that lets Vertex AI route your request to whichever region has capacity — similar in spirit to Bedrock's "cross-region inference profile." If you hit a quota or capacity error in one region, trying `global` or a different region is a reasonable first step.
2. **Quotas**: new projects get a default requests-per-minute quota per model, which is generally plenty for this course. If you do hit a quota error, go to **IAM & Admin → Quotas** in the console, filter for `aiplatform.googleapis.com`, and request an increase.
3. **Model IDs change over time.** We'll use `gemini-2.5-flash` as our default in the code below — check the [Vertex AI model list](https://cloud.google.com/vertex-ai/generative-ai/docs/models) for the current recommended ID if you hit a "model not found" error.

For now, you don't need to do anything else — just stick with the default model ID below and watch out for any quota issues.

## Part 3: Understanding Model Costs

### Gemini Model Pricing

The Gemini models offer different price points based on their capabilities:

- **Gemini Flash-Lite** - Most cost-effective for simple tasks
- **Gemini Flash** - Balanced cost for general use
- **Gemini Pro** - Higher cost for complex reasoning

For current pricing details, visit: [Vertex AI Generative AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

The pricing page will show you:
- Cost per million input tokens
- Cost per million output tokens
- Comparison across model tiers
- Regional pricing differences

Generally, Gemini Flash-Lite and Flash are very cost-effective options for most conversational AI use cases.

## Part 4: Update Your Code for Vertex AI

### Step 1: Update Requirements

Update `twin/backend/requirements.txt` — remove `openai` since we're not using it, and add the `google-genai` SDK (which supports both the Gemini Developer API and Vertex AI through one client):

```
fastapi
uvicorn
python-dotenv
python-multipart
google-cloud-storage
google-genai
pypdf
```

Note: We removed `openai` from the requirements.

### Step 2: Update the Server Code

Replace your `twin/backend/server.py` with this Vertex AI-enabled version:

```python
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
```

### Key Changes Explained

1. **Removed OpenAI import** - No longer using `from openai import OpenAI`
2. **Added a Vertex AI client** - Using `google-genai` with `vertexai=True` to connect to Vertex AI
3. **New `call_vertex_ai` function** - Handles Gemini's content/role format, and passes the system prompt cleanly via `system_instruction` rather than smuggling it in as a fake user message
4. **Model selection via environment variable** - Easy to switch between Gemini tiers
5. **Better error handling** - Specific handling for Vertex AI permission and model-not-found errors

## Part 5: Deploy to Cloud Run

### Step 1: Update Cloud Run Environment Variables

Since `requirements.txt` changed, rebuild and redeploy. From the `backend` directory:

```bash
cd backend

gcloud run deploy twin-api \
  --source . \
  --region us-central1 \
  --service-account twin-runtime@YOUR_PROJECT_ID.iam.gserviceaccount.com \
  --timeout 60 \
  --memory 512Mi \
  --set-env-vars CORS_ORIGINS=https://your-project-id.web.app,USE_GCS=true,GCS_BUCKET=twin-memory-your-suffix,GEMINI_MODEL_ID=gemini-2.5-flash,GCP_PROJECT_ID=YOUR_PROJECT_ID,GCP_REGION=us-central1
```

You can now drop `OPENAI_API_KEY` from your env vars entirely since we're not using it. Note the timeout is bumped to 60 seconds here, matching the more generous Lambda timeout used in the AWS version's Bedrock step — Gemini Pro can take a few seconds longer than Flash-Lite.

### Model ID Options

You can change `GEMINI_MODEL_ID` to any of these (check the [model list](https://cloud.google.com/vertex-ai/generative-ai/docs/models) for the exact current IDs):
- `gemini-2.5-flash-lite` - Fastest and cheapest
- `gemini-2.5-flash` - Balanced (recommended)
- `gemini-2.5-pro` - Most capable but more expensive

### Step 2: Test the Deployment

```bash
curl https://twin-api-abc123xyz-uc.a.run.app/health
```

You should see something like:

```json
{"status": "healthy", "use_gcs": true, "gemini_model": "gemini-2.5-flash"}
```

## Part 6: Test Your Vertex AI-Powered Twin

### Step 1: Test the Cloud Run URL Directly

Visit `https://twin-api-abc123xyz-uc.a.run.app/health` in your browser. You should see the Gemini model in the response.

### Step 2: Test via Firebase Hosting

1. Visit your Firebase Hosting URL: `https://your-project-id.web.app`
2. Start a conversation with your twin
3. Test that the chat is working properly - if you get a reply "Sorry, I encountered an error. Please try again" then see below
4. Verify that responses are coming through successfully

If your twin replies with an error, check Cloud Logging (see below) for the underlying exception. If it's a Vertex AI error, try switching `GEMINI_MODEL_ID` to a different tier, or try region `global` if you configured `GCP_REGION` for something narrower.

## Part 7: Cloud Monitoring and Logging

Now let's set up monitoring to track your Vertex AI usage and Cloud Run performance.

### Step 1: View Cloud Run Metrics

1. In the GCP Console, go to **Cloud Run**
2. Click on `twin-api`
3. Go to the **Metrics** tab
4. Check these key metrics:
   - ✅ Request count
   - ✅ Request latency
   - ✅ Container CPU/memory utilization
   - ✅ Container instance count

### Step 2: View Vertex AI Metrics

1. In the GCP Console, go to **Monitoring → Metrics Explorer**
2. Select the metric resource type **Vertex AI Publisher Model** (or search "aiplatform")
3. Monitor these metrics for your Gemini model:
   - **Model invocation count**
   - **Model invocation latency**
   - **Token count** (input and output)

### Step 3: View Cloud Run Logs

```bash
gcloud run services logs read twin-api --region us-central1 --limit 100
```

Or in the console: **Cloud Run → twin-api → Logs**. You can see:
- Each request
- Vertex AI calls
- Any errors or warnings
- Response times

### Step 4: Create a Monitoring Dashboard (Optional)

1. In the console, go to **Monitoring → Dashboards → Create Dashboard**
2. Name it `twin-monitoring`
3. Add charts for:
   - Cloud Run request count (Line, sum, 5 min)
   - Cloud Run request latency (Line, average, 5 min)
   - Cloud Run 5xx error count (Number, sum, 1 hour)
   - Vertex AI model invocation count (Line, sum, 5 min)

### Step 5: Set Up Cost Monitoring

1. Go to **Billing → Reports**
2. Filter by:
   - Service: Vertex AI
   - Time range: Last 7 days
3. You can see your Vertex AI costs accumulating

### Step 6: Create a Budget Alert (Recommended)

1. Go to **Billing → Budgets & alerts → Create budget**
2. Set:
   - Budget name: `twin-budget`
   - Monthly budget amount: $10 (or your preference)
   - Alert threshold: 80% and 100%
3. Enter your email for notifications (or connect a Pub/Sub topic for programmatic alerts)
4. Click **Finish**

## Part 8: Performance Comparison (Optional)

### Test Different Models

Let's compare the Gemini tiers. Update your Cloud Run environment variable `GEMINI_MODEL_ID` to test each:

```bash
gcloud run services update twin-api \
  --region us-central1 \
  --set-env-vars GEMINI_MODEL_ID=gemini-2.5-flash-lite
```

1. **Gemini Flash-Lite**
   - Fastest response (typically <1 second)
   - Good for simple Q&A
   - Lowest cost

2. **Gemini Flash**
   - Balanced performance (1-2 seconds)
   - Good for most conversations
   - Recommended for production

3. **Gemini Pro**
   - Most sophisticated responses (2-4 seconds)
   - Best for complex reasoning
   - Higher cost

### Monitoring Response Times

After testing each model, check Cloud Logging:

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="twin-api"' \
  --limit 50 --format json
```

Or use **Logs Explorer** in the console with a query filtering on `resource.type="cloud_run_revision"` and look at request latency in the generated request logs, grouped by time.

## Troubleshooting

### "Permission Denied" Errors

If you see permission denied errors:

1. Verify IAM permissions:
   - `twin-runtime` service account has `roles/aiplatform.user`
   - The Vertex AI API is enabled (`gcloud services list --enabled | grep aiplatform`)
2. Verify region:
   - Make sure `GCP_REGION` is a region where your chosen model is available

### "Model Not Found" Errors

1. Check the model ID is correct and current — check the [model list](https://cloud.google.com/vertex-ai/generative-ai/docs/models)
2. Verify the model is available in your configured region (try `global` or `us-central1` if unsure)

### High Latency Issues

If responses are slow:

1. Try Gemini Flash-Lite for faster responses
2. Check the Cloud Run timeout (should be 60+ seconds for Pro-tier models)
3. Review Cloud Logging for bottlenecks
4. Consider increasing Cloud Run memory/CPU (faster processing of the request/response cycle)

### Chat Not Working

1. Check Cloud Logging for specific errors
2. Test the Cloud Run service directly with `curl`
3. Verify all environment variables are set (`gcloud run services describe twin-api --region us-central1`)
4. Check CORS configuration

## Cost Optimization Tips

### Choosing the Right Model

- **Gemini Flash-Lite**: Use for greetings, simple FAQs, basic queries
- **Gemini Flash**: Use for standard conversations, general Q&A
- **Gemini Pro**: Reserve for complex analysis, detailed responses

### Reducing Costs

1. **Limit context window** - We're sending the last 50 messages; reduce if possible
2. **Cache common responses** - Store FAQs and serve them without a model call
3. **Set max tokens appropriately** - We use 2000; adjust based on needs
4. **Monitor usage** - Set up billing alerts
5. **Use Cloud Run concurrency and scale-to-zero** - Avoid paying for idle capacity

### Estimated Monthly Costs

Your costs will depend on:
- Number of conversations per month
- Average conversation length
- Choice of Gemini model
- Cloud Run and Cloud Storage usage

Check the [Vertex AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing) page and the [GCP pricing calculator](https://cloud.google.com/products/calculator) to estimate your specific usage costs.

## What You've Accomplished Today!

- ✅ Transitioned from OpenAI to Vertex AI
- ✅ Configured IAM permissions for AI services
- ✅ Implemented three different Gemini model tiers
- ✅ Deployed the Vertex AI integration to Cloud Run
- ✅ Set up Cloud Monitoring and Logging
- ✅ Created cost tracking and budget alerts
- ✅ Learned enterprise AI deployment patterns on GCP

## Architecture Recap

Your updated architecture:

```
User Browser
    ↓ HTTPS
Firebase Hosting (CDN)
    ↓ HTTPS API Calls
Cloud Run (Backend)
    ↓
    ├── Vertex AI / Gemini (AI responses)  ← NEW!
    └── Cloud Storage Bucket (persistence)
```

All services now stay within GCP, providing:
- Lower latency (no external API calls)
- Better security (IAM integration, no API keys to manage)
- Potential cost savings
- Unified billing and monitoring

## Next Steps

Tomorrow (Day 4), we'll:
- Introduce Infrastructure as Code with Terraform
- Automate the entire deployment process
- Implement environment management (dev/staging/prod)
- Add advanced features
- Set up proper secret management

Your Digital Twin is now powered entirely by GCP services - a true cloud-native application!

## Resources

- [Vertex AI Documentation](https://cloud.google.com/vertex-ai/docs)
- [Vertex AI Generative AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)
- [Gemini Model Documentation](https://cloud.google.com/vertex-ai/generative-ai/docs/models)
- [Cloud Monitoring Documentation](https://cloud.google.com/monitoring/docs)
- [GCP Cost Management](https://cloud.google.com/cost-management)

Congratulations on successfully integrating Vertex AI! 🚀
