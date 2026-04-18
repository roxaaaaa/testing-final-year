import asyncio
import logging
import os
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.requests import Request

from model_service import (
    AppConfig,
    DID_API_KEY,
    DID_AVATAR_ENABLED,
    DataConfig,
    FeedbackGenerator,
    GenerationConfig,
    ModelConfig,
    QuestionGenerator,
    VideoGenerator,
    did_avatar_permission_denied,
)

load_dotenv()

MODEL_NAME = os.getenv("MODEL_NAME", "llama3.1:8b")
CHATGPT_MODEL = os.getenv("CHATGPT_MODEL", "gpt-4o-mini")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


def _cors_allow_origins() -> list[str]:
    """Same dev app may be opened as localhost or 127.0.0.1; browsers treat them as different origins."""
    from urllib.parse import urlparse

    base = FRONTEND_URL.rstrip("/")
    origins = {base}
    try:
        p = urlparse(base)
        if p.hostname == "localhost":
            origins.add(base.replace("://localhost", "://127.0.0.1", 1))
        elif p.hostname == "127.0.0.1":
            origins.add(base.replace("://127.0.0.1", "://localhost", 1))
    except Exception:
        pass
    return list(origins)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Agricultural Science Exam Assistant",
    description="API for generating exam questions, feedback, and D-ID avatar videos for practice",
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log raw request body and validation errors to help debug 422 responses."""
    body_bytes = await request.body()
    try:
        body_text = body_bytes.decode()
    except Exception:
        body_text = str(body_bytes)

    logger.error("Validation Error - Body: %s, Errors: %s", body_text, exc.errors())

    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors(), "raw_body": body_text},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TopicRequest(BaseModel):
    """Request model for generating exam questions."""

    topic_name: str
    level: Literal["higher", "ordinary"] = "ordinary"
    persona: Literal["student", "teacher"] = "student"


class FeedbackRequest(BaseModel):
    """Request model for generating feedback."""

    question: str
    answer: str
    level: Literal["higher", "ordinary"] = "ordinary"
    use_video: bool = True


@app.get("/", tags=["Health"])
async def root():
    """Health check endpoint."""
    return {
        "status": "Server is running",
        "service": "Agricultural Science Exam Assistant",
        "d_id_configured": bool(DID_API_KEY),
        "d_id_avatar_enabled": DID_AVATAR_ENABLED,
        "env": os.getenv("ENV", "development"),
    }


@app.get("/health", tags=["Health"])
async def health():
    """Detailed health check."""
    return {
        "status": "healthy",
        "ollama_available": bool(OLLAMA_BASE_URL),
        "openai_available": bool(os.getenv("OPENAI_API_KEY")),
        "d_id_configured": bool(DID_API_KEY),
        "d_id_avatar_enabled": DID_AVATAR_ENABLED,
    }


@app.post("/api/ai/generate_questions", tags=["Questions"])
async def generate_questions(data: TopicRequest):
    """
    Generate exam questions for a given topic and level.
    Question count follows persona: 3 for students, 5 for teachers (client-supplied).
    """
    num_questions = 3 if data.persona == "student" else 5
    logger.info(
        "Generating questions: topic=%s, level=%s, persona=%s, num_questions=%s",
        data.topic_name,
        data.level,
        data.persona,
        num_questions,
    )

    try:
        config = AppConfig(
            model=ModelConfig(model_name=MODEL_NAME, api_key="ollama"),
            generation=GenerationConfig(num_questions=num_questions),
            data=DataConfig(topic=data.topic_name, level=data.level),
        )

        generator = QuestionGenerator(config)
        generated_questions = generator.generate_questions()

        if not generated_questions:
            raise HTTPException(status_code=404, detail="No questions were generated")

        return {
            "questions": generated_questions,
            "count": len(generated_questions),
            "level": data.level,
            "topic": data.topic_name,
            "status": "success",
        }

    except ValueError as e:
        logger.error("Validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating questions: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/ai/generate_feedback", tags=["Feedback"])
async def generate_feedback_ai(content: FeedbackRequest):
    """
    Generate feedback for a student answer; optionally a D-ID avatar video when use_video and DID_API_KEY are set.
    """
    logger.info("Generating feedback: level=%s, use_video=%s", content.level, content.use_video)

    try:
        config = AppConfig(
            model=ModelConfig(model_name=CHATGPT_MODEL, base_url=None),
            generation=None,
            data=DataConfig(
                question=content.question,
                answer=content.answer,
                level=content.level,
            ),
        )

        use_video = (
            content.use_video
            and bool(DID_API_KEY)
            and DID_AVATAR_ENABLED
            and not did_avatar_permission_denied()
        )
        if use_video:
            generator = FeedbackGenerator(config, use_video=True)
            result = await asyncio.to_thread(generator.generate_feedback_with_video)
            return {
                "feedback": result["feedback_text"],
                "video_url": result.get("video_url"),
                "talk_id": result.get("talk_id"),
                "video_status": result.get("video_status"),
                "has_video": bool(result.get("video_url")),
            }

        generator = FeedbackGenerator(config, use_video=False)
        feedback = await asyncio.to_thread(generator.generate_feedback)

        video_status_ai = "skipped" if content.use_video else "not_used"

        return {
            "feedback": feedback,
            "video_url": None,
            "talk_id": None,
            "video_status": video_status_ai,
            "has_video": False,
        }

    except ValueError as e:
        logger.error("Validation error: %s", e)
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Error generating feedback: %s", e)
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/d-id/video-status/{talk_id}", tags=["D-ID"])
async def get_video_status(talk_id: str):
    """Proxied D-ID Talk job status: GET /talks/{id} (polling)."""
    if not DID_API_KEY:
        raise HTTPException(status_code=503, detail="D-ID not configured")
    try:
        video_gen = VideoGenerator()
        return video_gen.get_video_status(talk_id)
    except Exception as e:
        logger.error("D-ID video status error: %s", e)
        raise HTTPException(status_code=502, detail=str(e)) from e


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
