from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from pydantic import BaseModel

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL


app = FastAPI(
    title="ASTU CampusGuide AI API",
    description="Backend API for the ASTU CampusGuide AI project.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class GeminiTestResponse(BaseModel):
    message: str
    model: str
    reply: str


@app.get("/")
def root():
    return {
        "name": "ASTU CampusGuide AI",
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "campusguide-api",
    }


@app.post("/api/ai/test", response_model=GeminiTestResponse)
def test_gemini():
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is not configured.",
        )

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=(
                "You are testing ASTU CampusGuide AI. "
                "Reply with one short sentence welcoming an ASTU student."
            ),
        )

        if not response.text:
            raise HTTPException(
                status_code=502,
                detail="Gemini returned an empty response.",
            )

        return GeminiTestResponse(
            message="Gemini connection successful.",
            model=GEMINI_MODEL,
            reply=response.text,
        )

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            status_code=502,
            detail=(
                "Gemini request failed. Check the API key, "
                "model availability, quota, and network connection."
            ),
        ) from None
