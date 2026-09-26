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

The local default resume is `Divya_Jain_Resume_.pdf` in this folder. Resume PDFs
under `backend/` are ignored by Git and are not uploaded with the source. For a
deployment, upload the PDF privately to the host's persistent/private file
storage and set `RESUME_PATH` to its absolute mounted path. Keep the filename
and access private; do not paste the resume contents into source code or commit
the PDF. The host must make that file available to the backend at runtime.

On Vercel, serverless function filesystems are not suitable for a private file
that must be uploaded after deployment. Use private object storage and adapt the
backend to fetch the PDF securely, or deploy the backend on a host with a private
persistent disk (such as a Render disk) and set `RESUME_PATH` to that disk path.