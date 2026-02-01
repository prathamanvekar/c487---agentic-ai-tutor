# Local Dev + Basic Tests

This project has:

- Backend: FastAPI (in `backend/`)
- Frontend: Next.js (in `frontend/`)

## 1) Install backend deps

From the repo root:

### Windows PowerShell

```powershell
# (optional) create & activate venv
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1

# install deps
cd ..
pip install -r requirements.txt
```

### Git Bash

```bash
cd backend
python -m venv venv
source venv/Scripts/activate

cd ..
pip install -r requirements.txt
```

## 2) Start backend

Run from the `backend/` folder:

```bash
cd backend
uvicorn main:app --reload
```

Notes:

- Set `JWT_SECRET` in `backend/.env`:
  - `JWT_SECRET="replace_with_a_long_random_secret"`

## 3) Start frontend

Run from the `frontend/` folder:

```bash
cd frontend
npm install
npm run dev
```

Frontend:

- http://localhost:3000
  Backend:
- http://127.0.0.1:8000

## 4) Basic API tests (curl)

### 4.1 Upload a PDF

```bash
curl -F "course_id=1" -F "file=@/path/to/kech101.pdf" http://127.0.0.1:8000/upload_file
```

Response example:

```json
{
  "saved_path": "./uploads/1700000000_kech101.pdf",
  "filename": "kech101.pdf",
  "course_id": 1
}
```

### 4.2 Parse curriculum (TOC)

Replace `saved_path` with the value returned from `/upload_file`.

```bash
curl -X POST http://127.0.0.1:8000/parse_curriculum \
  -H "Content-Type: application/json" \
  -d '{"saved_path":"./uploads/<timestamp>_kech101.pdf","course_id":1,"parse_mode":"toc"}'
```

### 4.3 Ingest vectors

```bash
curl -X POST http://127.0.0.1:8000/ingest_vectors \
  -H "Content-Type: application/json" \
  -d '{"course_id":1,"filepaths":["./uploads/<timestamp>_kech101.pdf"]}'
```

### 4.4 Teach (course-specific RAG)

```bash
curl -X POST http://127.0.0.1:8000/teach \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1,"query":"Explain chapter 1"}'
```

### 4.5 Generate a quiz

```bash
curl -X POST http://127.0.0.1:8000/quiz \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1,"query":"Chapter 1"}'
```

### 4.6 Grade a quiz

```bash
curl -X POST http://127.0.0.1:8000/grade \
  -H "Content-Type: application/json" \
  -d '{"student_id":1,"course_id":1,"topic":"Chapter 1","question":"...","student_answer":"A","correct_answer":"B"}'
```

## 5) Inspect the SQLite DB

The SQLite file is `backend/student_data.db` (created on first run).

### Open sqlite3

```bash
sqlite3 backend/student_data.db
```

### Useful commands

```sql
.tables
.schema students
.schema curriculum_topics
.schema knowledge_state

SELECT * FROM students;
SELECT * FROM curriculum_topics WHERE course_id = 1 ORDER BY topic_order;
SELECT * FROM knowledge_state WHERE student_id = 1 AND course_id = 1;
SELECT * FROM quiz_results WHERE student_id = 1 ORDER BY timestamp DESC;
```

## (Optional) Auth smoke test

### Signup

```bash
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","learning_style":"visual"}'
```

### Login

```bash
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice"}'
```

### Use token

```bash
curl -X POST http://127.0.0.1:8000/teach \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"course_id":1,"query":"Explain chapter 1"}'
```
