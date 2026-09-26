# Candidate Chat Backend

FastAPI service for the interview-practice frontend. It loads the resume PDF
next to `main.py`, parses it once per server process, and answers questions
using the configured Groq model.

## Setup

From the `d3` folder, install the backend dependencies into the project venv:

```powershell
.\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Copy `.env.example` to `.env` for local development, then add up to three Groq
API keys. The backend
tries the next key after authentication, timeout, connection, or provider-server
failures. It does not rotate keys on `403` or `429` responses.

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_API_KEY2=your_second_groq_api_key
GROQ_API_KEY3=your_third_groq_api_key
```

The second and third keys are optional. Keep the values private and do not
commit `.env` to source control. For deployment, set `APP_ENV=production`,
configure the Groq keys and a random `APP_ACCESS_TOKEN` of at least 32
characters through the hosting provider's secret manager, and set `CORS_ORIGINS`
to the exact frontend origin or comma-separated origins, for example
`https://candidate.example.com`. Production refuses to start without the access
token and does not load the local `.env` file.
## Run

From the `d3` folder:

```powershell
Set-Location backend
..\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001
```

In development, interactive API documentation is available at
`http://127.0.0.1:8001/docs`. It is disabled in production. The frontend uses
localhost for development and same-origin `/` and `/chat` requests in production;
configure the hosting reverse proxy to serve the frontend and route `/chat` to
the backend over HTTPS.

In production, `POST /chat` requires `Authorization: Bearer <APP_ACCESS_TOKEN>`.
The frontend asks for this token and keeps it in memory only; provide it only to
trusted users over a secure channel. The API also limits chat to 10 requests per
minute per client address in each backend process. This in-memory limit resets on
restarts and is not shared across workers. Configure an additional rate limit at
the hosting edge, and ensure the reverse proxy forwards reliable client
addresses. CORS is not an authentication mechanism.

## Routes

- `GET /` returns a backend health message.
- `POST /chat` accepts `{"question": "Tell me about yourself."}` and returns
  `{"answer": "..."}`.

The current default resume is `Divya_Jain_Resume_.pdf` in this folder and is
committed in this repository, so Render deploys it with the backend source. This
makes the PDF publicly accessible through the repository. If you later want to
keep it private, remove it from Git and its history, then store it in the host's
private file/object storage and set `RESUME_PATH` to its runtime path.

On Vercel, serverless function filesystems are not suitable for a private file
that must be uploaded after deployment. Use private object storage and adapt the
backend to fetch the PDF securely, or deploy the backend on a host with a private
persistent disk (such as a Render disk) and set `RESUME_PATH` to that disk path.

## Deploy to Render and Vercel

The repository includes a Render Blueprint (`render.yaml`) and Vercel
configuration (`vercel.json`). The Render service is named
`d3-resume-chat-api`; Vercel proxies `/api` requests to
`https://d3-resume-chat-api.onrender.com`.

1. In Render, create a **Blueprint** from the `d3` GitHub repository and select
  `render.yaml`. During initial setup, enter `APP_ACCESS_TOKEN` and the
  replacement Groq keys when prompted. Never put their values in Git. If the
  Render service name is unavailable and you rename it, change the matching
  destination hostname in `vercel.json` and push that change.
2. Wait for the Render service to deploy and confirm its root health check
  returns `Candidate Chat API is running.`
3. In Vercel, import the same repository with the project root set to the `d3`
  repository root. `vercel.json` publishes `frontend/` and proxies its `/api`
  requests to Render. Deploy after the Render hostname is final.
4. Open the Vercel domain and enter the `APP_ACCESS_TOKEN` value you set in
  Render. The token is held only in page memory.

The Blueprint uses Render's free web-service plan, which may sleep while idle
and take longer to respond to the first request. Upgrade the plan if you need
always-on service. The resume PDF is currently part of this Git repository, so
the deployed Render backend receives it with the source. Use private object
storage and remove the PDF from Git history if it should no longer be public.