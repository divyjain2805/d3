import json
import logging
import os
import secrets
import time
from collections import deque
from functools import lru_cache
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from groq import Groq
from pydantic import BaseModel, Field, ValidationError
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESUME_PATH = Path(__file__).resolve().with_name("Divya_Jain_Resume_.pdf")
RESUME_PATH = Path(os.getenv("RESUME_PATH", str(DEFAULT_RESUME_PATH))).expanduser()
if not RESUME_PATH.is_absolute():
    RESUME_PATH = PROJECT_ROOT / RESUME_PATH
MODEL = "openai/gpt-oss-20b"
logger = logging.getLogger(__name__)

APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"
if not IS_PRODUCTION:
    load_dotenv(PROJECT_ROOT / ".env")
ACCESS_TOKEN = os.getenv("APP_ACCESS_TOKEN", "")
if IS_PRODUCTION and len(ACCESS_TOKEN) < 32:
    raise RuntimeError("Set APP_ACCESS_TOKEN to a random secret of at least 32 characters in production.")

configured_origins = os.getenv("CORS_ORIGINS", "")
allowed_origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
if not IS_PRODUCTION and not allowed_origins:
    allowed_origins = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

app = FastAPI(
    title="Candidate Chat API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

CHAT_REQUEST_LIMIT = 10
CHAT_RATE_WINDOW_SECONDS = 60
chat_request_times: dict[str, deque[float]] = {}
chat_rate_lock = Lock()


def require_chat_access(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    if IS_PRODUCTION:
        scheme, _, provided_token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(provided_token, ACCESS_TOKEN):
            raise HTTPException(status_code=401, detail="A valid access token is required.")

    client_ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    with chat_rate_lock:
        requests = chat_request_times.setdefault(client_ip, deque())
        while requests and now - requests[0] >= CHAT_RATE_WINDOW_SECONDS:
            requests.popleft()
        if len(requests) >= CHAT_REQUEST_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Chat request limit reached. Please try again in a minute.",
                headers={"Retry-After": str(CHAT_RATE_WINDOW_SECONDS)},
            )
        requests.append(now)

        if len(chat_request_times) > 10000:
            for ip, timestamps in list(chat_request_times.items()):
                if not timestamps or now - timestamps[-1] >= CHAT_RATE_WINDOW_SECONDS:
                    chat_request_times.pop(ip, None)
            while len(chat_request_times) > 10000:
                chat_request_times.pop(next(iter(chat_request_times)))


class Experience(BaseModel):
    company: str | None = None
    role: str | None = None
    duration: str | None = None
    description: str | None = None
    skills_used: list[str] = Field(default_factory=list)


class Resume(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    total_experience_years: float | None = None
    skills: list[str] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


def create_completion(messages, response_format: dict[str, str] | None = None):
    api_keys = list(dict.fromkeys(
        key.strip()
        for key in (
            os.getenv("GROQ_API_KEY"),
            os.getenv("GROQ_API_KEY2"),
            os.getenv("GROQ_API_KEY3"),
        )
        if key and key.strip()
    ))
    if not api_keys:
        raise HTTPException(
            status_code=503,
            detail="The backend is missing Groq API keys in its environment configuration.",
        )

    request_options = {"model": MODEL, "messages": messages}
    if response_format is not None:
        request_options["response_format"] = response_format

    last_error = None
    for key_number, api_key in enumerate(api_keys, start=1):
        try:
            client = Groq(api_key=api_key, max_retries=0)
            return client.chat.completions.create(**request_options)
        except Exception as exc:
            status_code = getattr(exc, "status_code", None)
            retryable = (
                status_code in {401, 408}
                or isinstance(status_code, int) and 500 <= status_code < 600
                or type(exc).__name__ in {"APIConnectionError", "APITimeoutError"}
            )
            if not retryable:
                raise

            last_error = exc
            logger.warning(
                "Groq key %d of %d failed with %s; trying the next key.",
                key_number,
                len(api_keys),
                type(exc).__name__,
            )

    if last_error is not None:
        raise last_error
    raise HTTPException(status_code=503, detail="No Groq API keys are configured.")




def parse_resume(resume_text: str) -> Resume:
    schema = Resume.model_json_schema()
    system_prompt = f"""
You are an expert resume parser. Extract information based on meaning, not only
section headings. Experience can also appear under work history, employment,
internships, or similar headings. Extract skills mentioned throughout the resume.

Return only valid JSON matching this schema:
{schema}

Do not invent information. Use null for unavailable scalar values and empty lists
when no information is available. Include internships in experiences.
"""
    response = create_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Parse the following resume:\n\n{resume_text}"},
        ],
        response_format={"type": "json_object"},
    )
    raw_output = response.choices[0].message.content
    if not raw_output:
        raise HTTPException(status_code=502, detail="The resume parser returned an empty response.")
    try:
        return Resume.model_validate(json.loads(raw_output))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=502, detail="The resume parser returned invalid data.") from exc


def read_pdf(file_path: Path) -> str:
    if not file_path.is_file():
        raise HTTPException(status_code=500, detail="The configured resume PDF was not found.")

    reader = PdfReader(file_path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    if not text:
        raise HTTPException(status_code=422, detail="No readable text was found in the resume PDF.")
    return text


@lru_cache(maxsize=1)
def load_resume() -> Resume:
    return parse_resume(read_pdf(RESUME_PATH))


def ask_candidate(question: str, resume: Resume) -> str:
    system_prompt = f"""
You are an AI assistant representing a job candidate. Answer as if HR is
interviewing this candidate, using only the information below. Never invent
details. If information is unavailable, say: "I don't have enough information
to answer that." Keep the answer professional and natural.

Candidate information:
{resume.model_dump_json(indent=2)}
"""
    response = create_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ],
    )
    answer = response.choices[0].message.content
    if not answer:
        raise HTTPException(status_code=502, detail="The assistant returned an empty answer.")
    return answer


@app.get("/")
def home() -> dict[str, str]:
    return {"message": "Candidate Chat API is running."}


@app.post("/chat")
def chat(
    request: ChatRequest,
    _: None = Depends(require_chat_access),
) -> dict[str, str]:
    try:
        return {"answer": ask_candidate(request.question, load_resume())}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Chat request failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=502,
            detail="The assistant could not complete the request. Check the backend logs.",
        ) from exc