# Setup (Local Dev)

This repo contains a **FastAPI backend** (`backend/`) and a **Next.js frontend** (`frontend/`).

You mentioned you will NOT send these generated/runtime artifacts:

- SQLite DB (`backend/student_data.db`)
- Chroma vector store (`db_chroma/` and/or `backend/db_chroma/` depending on where it is created)
- Uploads folder (`backend/uploads/`)
- Python venv (`backend/venv/`)
- Node modules (`frontend/node_modules/`)

…and you **WILL** include the `backend/data/` folder for testing.

This guide assumes a fresh clone / fresh unzip with only source code + `backend/data/` present.

---

## 0) Prerequisites

### Required

- **Python 3.10+** (3.11 recommended)
- **Node.js 18+** (Node 20 LTS recommended)
- **npm** (ships with Node)

### Accounts / API keys

This project uses Groq via `langchain-groq`.

- Create a Groq API key and set `GROQ_API_KEY`.

---

## 1) Backend setup (Windows)

Open a terminal at the **project root**.

### 1.1 Create a virtual environment

PowerShell:

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
cd ..
```

Git Bash:

```bash
cd backend
python -m venv venv
source venv/Scripts/activate
cd ..
```

### 1.2 Install Python dependencies

```bash
pip install -r requirements.txt
```

### 1.3 Create backend environment file

Create `backend/.env`:

```env
# Required
JWT_SECRET="replace_with_a_long_random_secret"
GROQ_API_KEY="your_groq_api_key"

# Optional
# GROQ_MODEL="llama-3.1-8b-instant"
```

Notes:

- `JWT_SECRET` is required for auth endpoints.
- `GROQ_API_KEY` is required for curriculum parsing / teaching / quiz generation.

### 1.4 Run the backend

```bash
cd backend
uvicorn main:app --reload
```

Backend should be available at:

- http://127.0.0.1:8000

---

## 2) Frontend setup

Open a new terminal at the project root.

```bash
cd frontend
npm install
npm run dev
```

Frontend should be available at:

- http://localhost:3000

If you need to point the frontend to a different backend URL, set:

- `NEXT_PUBLIC_API_URL` (see `frontend/app/lib/api.ts`)

Example (PowerShell):

```powershell
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"
npm run dev
```

---

## 3) “Clean slate” reset (recommended before testing)

If you want to reset everything like a brand new install:

### 3.1 Stop servers

- Stop frontend dev server (Ctrl+C)
- Stop backend (Ctrl+C)

### 3.2 Delete generated backend state

From the project root:

PowerShell:

```powershell
Remove-Item -Force -ErrorAction SilentlyContinue backend\student_data.db
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue backend\uploads
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue db_chroma
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue backend\db_chroma
```

Git Bash:

```bash
rm -f backend/student_data.db
rm -rf backend/uploads
rm -rf db_chroma backend/db_chroma
```

### 3.3 Clear browser storage

In Chrome:

- DevTools → Application → Storage → Local Storage → `http://localhost:3000`
- Delete keys: `token`, `student_id`

Then restart backend + frontend.

---

## 4) End-to-end testing (through the frontend)

This is the intended flow after a clean slate.

### 4.1 Create an account

1. Go to http://localhost:3000/register
2. Register (username/password/learning style)
3. Expected: redirect to **Dashboard**

### 4.2 Create a course

1. From Dashboard, click **Lobby** (or go to http://localhost:3000/lobby)
2. Create a course
3. Expected: redirect to **Course Setup** page: `http://localhost:3000/course/<id>/setup`

### 4.3 Upload curriculum PDF (index)

On the setup page:

1. Upload **one** curriculum/index PDF as the curriculum file
2. Click **Parse curriculum**
3. Expected: Curriculum list populates (chapters/topics). On setup page, there should be **no “Start lesson”** button.

### 4.4 Upload content PDFs (multiple)

On the same setup page:

1. Upload all chapter/content PDFs (multi-select)
2. Click **Ingest content**
3. Expected: vectors are created for the course

### 4.5 Start learning

1. Click **Start learning** (enabled only when curriculum + vectors exist)
2. This opens `http://localhost:3000/course/<id>`
3. Expected:
   - Curriculum list shows **Start lesson** buttons
   - Clicking Start lesson sets the active topic for the chat session

### 4.6 Verify “course aware” tutoring

1. Click Start lesson on a chapter
2. Ask a follow-up question in chat
3. Expected: answers are grounded in your uploaded course content

### 4.7 Verify quizzes are relevant

1. With an active chapter selected, click **Take Quiz**
2. Expected: quiz is generated from the current course context (not unrelated defaults)
3. Pick an option to grade it

---

## 5) Using the included `backend/data/` folder

The repo may include example PDFs under `backend/data/`.

Recommended usage:

- Use those PDFs via the **setup page uploader** (curriculum PDF → parse; content PDFs → ingest).
- You do NOT need to manually provide file paths.

---

## 6) Troubleshooting

### Auth / 401 errors

- Ensure `backend/.env` has `JWT_SECRET`
- Ensure your browser has a `token` in Local Storage
- Ensure backend is running on the same URL configured in frontend

### Curriculum parse fails

- Ensure `GROQ_API_KEY` is set
- Check backend terminal logs for the exact exception

### Chat is generic / not grounded

- Make sure you ingested content PDFs
- Make sure you clicked **Start lesson** (learning page) before asking vague prompts

### CORS / network errors

- Confirm backend: http://127.0.0.1:8000
- Confirm frontend: http://localhost:3000

---

## 7) What gets regenerated automatically

On first run, the project will recreate:

- `backend/student_data.db` (SQLite)
- `backend/uploads/` (uploaded PDFs)
- `db_chroma/course_<id>/...` (per-course vector DB)

Those are safe to delete and will be recreated.
