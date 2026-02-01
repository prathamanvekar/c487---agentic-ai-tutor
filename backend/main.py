import json
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Query, Depends, Header
from pydantic import BaseModel

from passlib.context import CryptContext

from fastapi.middleware.cors import CORSMiddleware

from database import (
    save_quiz_result,
    get_student_mastery,
    save_curriculum_topic,
    get_course_topics,
    get_knowledge_state,
    get_conn,
    get_knowledge_state_entry,
    update_knowledge_state,
    create_student,
    get_student_by_username,
    create_course,
    list_courses_for_owner,
    get_career_recommendation,
    upsert_career_recommendation,
)

from ingest import ingest_files_for_course

from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser

# -------------------------------------------------
# 1. Load Environment Variables
# -------------------------------------------------
load_dotenv()

# -------------------------------------------------
# JWT Auth (MVP scaffold)
# -------------------------------------------------
# Install deps:
#   pip install python-jose[cryptography] passlib[bcrypt]
# .env:
#   JWT_SECRET="replace_with_a_long_random_secret"

JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 60 * 24 * 7  # 7 days


def _create_access_token(student_id: int) -> str:
    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET missing. Set JWT_SECRET in .env")

    now = datetime.now(timezone.utc)
    payload = {
        "student_id": student_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=JWT_EXPIRES_MINUTES)).timestamp()),
    }

    try:
        from jose import jwt
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"python-jose is required for JWT: {str(e)}")

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Optional[int]:
    """Optional auth dependency.

    - If Authorization header is missing: returns None (keeps MVP endpoints working)
    - If present but invalid: raises 401
    - If valid: returns student_id from JWT
    """
    if not authorization:
        return None

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization header. Use 'Bearer <token>'.")

    token = parts[1].strip()
    try:
        from jose import jwt, JWTError
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"python-jose is required for JWT: {str(e)}")

    if not JWT_SECRET:
        raise HTTPException(status_code=500, detail="JWT_SECRET missing. Set JWT_SECRET in .env")

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        student_id = payload.get("student_id")
        if student_id is None:
            raise HTTPException(status_code=401, detail="Token missing student_id")
        return int(student_id)
    except HTTPException:
        raise
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")


def _require_user_id(current_student_id: Optional[int]) -> int:
    if current_student_id is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return int(current_student_id)


class CreateCourseRequest(BaseModel):
    title: str
    description: str = ""


# -------------------------------------------------
# 2. Initialize FastAPI
# -------------------------------------------------
app = FastAPI(title="AI Tutor Agent")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins (for dev only)
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods
    allow_headers=["*"], # Allows all headers
)

# -------------------------------------------------
# 2.1 Create uploads folder if it doesn't exist
# -------------------------------------------------
UPLOADS_DIR = "./uploads"
os.makedirs(UPLOADS_DIR, exist_ok=True)


# -------------------------------------------------
# 2.2 Courses: list/create (Lobby)
# -------------------------------------------------
@app.get("/courses")
async def list_courses_endpoint(
    current_student_id: Optional[int] = Depends(get_current_user),
):
    student_id = _require_user_id(current_student_id)
    courses = list_courses_for_owner(student_id)
    return {"courses": courses}


@app.post("/courses")
async def create_course_endpoint(
    request: CreateCourseRequest,
    current_student_id: Optional[int] = Depends(get_current_user),
):
    student_id = _require_user_id(current_student_id)

    title = (request.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Course title required")

    course_id = create_course(
        title=title,
        description=(request.description or "").strip(),
        owner_student_id=student_id,
    )
    return {
        "course": {
            "id": course_id,
            "title": title,
            "description": request.description,
            "owner_student_id": student_id,
        }
    }

# -------------------------------------------------
# 3. Setup the AI (LLM)
# -------------------------------------------------
llm = ChatGroq(
    model="llama-3.1-8b-instant",
    temperature=0.7
)


# -------------------------------------------------
# 4. Connect to Vector Database (Chroma)
# -------------------------------------------------
embedding_function = HuggingFaceEmbeddings(
    model_name="all-MiniLM-L6-v2"
)

vector_store = Chroma(
    persist_directory="db_chroma",
    embedding_function=embedding_function
)

retriever = vector_store.as_retriever()


# -------------------------------------------------
# 5. Prompt Template
# -------------------------------------------------
system_prompt = (
    "You are an AI tutor. Answer ONLY using the given context. "
    "If the answer is not in the context, reply: "
    "'This topic is not covered in the course material.' "
    "Do NOT use outside knowledge.\n\n"
    "{context}"
)


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}")
    ]
)


# -------------------------------------------------
# 6. RAG Pipeline (Modern LCEL Style)
# -------------------------------------------------

def format_docs(docs):
    """Convert retrieved docs into a single string"""
    return "\n\n".join(doc.page_content for doc in docs)


rag_chain = (
    {
        "context": retriever | format_docs,
        "input": RunnablePassthrough(),
    }
    | prompt
    | llm
    | StrOutputParser()
)

# =================================================
# PHASE 3: ASSESSMENT AGENT (UPGRADED)
# =================================================

# 1. The Quiz Prompt (Strict JSON)
quiz_system_prompt = (
    "You are a strict Examiner Agent. "
    "Based ONLY on the provided context, generate ONE multiple-choice question. "
    "Return the output as valid JSON with the following keys: "
    "question, options (a list of 4 strings), and correct_answer (the index 0-3 of the correct option). "
    "\n\n"
    "Context: {context}"
)

quiz_prompt_template = ChatPromptTemplate.from_messages(
    [
        ("system", quiz_system_prompt),
        ("human", "Generate a quiz about: {input}")
    ]
)

# 2. The Quiz Chain (Now returns JSON object, not string)
quiz_chain = (
    {
        "context": retriever | format_docs,
        "input": RunnablePassthrough(),
    }
    | quiz_prompt_template
    | llm
    | JsonOutputParser()  # <--- MAGIC CHANGE
)

# =================================================
# =================================================
# PHASE 3.5: THE GRADING AGENT
# =================================================

# 1. The Grader Prompt
grader_system_prompt = (
    "You are a friendly Tutor. "
    "The student answered a multiple-choice question. "
    "Here is the question: {question} \n"
    "Here is the correct answer: {correct_answer} \n"
    "Here is the student's answer: {student_answer} \n\n"
    "Compare the student's answer to the correct answer. "
    "If they are correct, congratulate them briefly. "
    "If they are incorrect, explain WHY they are wrong and what the right answer is, based on the question context. "
    "Keep it short (2 sentences max)."
)

grader_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", grader_system_prompt),
        ("human", "Grade this.")
    ]
)

# 2. The Grading Chain
grader_chain = grader_prompt | llm | StrOutputParser()
# -------------------------------------------------
# 7. API Request Model
# -------------------------------------------------
class ChatTurn(BaseModel):
    role: str
    content: str


class QuestionRequest(BaseModel):
    student_id: int = 1
    query: str
    course_id: Optional[int] = None
    active_topic: Optional[str] = None
    chat_history: Optional[list[ChatTurn]] = None


class IngestVectorsRequest(BaseModel):
    course_id: int
    filepaths: Optional[list[str]] = None


def _normalize_path_for_api(path: str) -> str:
    # Make paths consistent for the frontend (Windows-safe)
    return (path or "").replace("\\", "/")


def _course_upload_dir(course_id: int, file_kind: str) -> str:
    safe_kind = (file_kind or "").strip().lower()
    if safe_kind not in {"curriculum", "content"}:
        raise HTTPException(status_code=400, detail="file_kind must be 'curriculum' or 'content'")
    return os.path.join(UPLOADS_DIR, f"course_{course_id}", safe_kind)


def _list_course_uploaded_pdfs(course_id: int, file_kind: str) -> list[str]:
    folder = _course_upload_dir(course_id, file_kind)
    if not os.path.exists(folder):
        return []
    files: list[str] = []
    for name in os.listdir(folder):
        if not name.lower().endswith(".pdf"):
            continue
        files.append(os.path.abspath(os.path.join(folder, name)))
    files.sort()
    return files


def _latest_course_uploaded_pdf(course_id: int, file_kind: str) -> Optional[str]:
    files = _list_course_uploaded_pdfs(course_id, file_kind)
    if not files:
        return None
    try:
        return max(files, key=lambda p: os.path.getmtime(p))
    except Exception:
        return files[-1]


def _is_generic_teach_query(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    generic_phrases = {
        "teach me",
        "teach me this",
        "teach me this topic",
        "teach me a topic",
        "start",
        "start lesson",
        "help",
        "help me",
        "help me learn",
        "what should i learn",
        "what should i learn today",
    }
    if q in generic_phrases:
        return True
    # Very short prompts are usually not a real topic.
    if len(q.split()) <= 2 and q in {"teach", "topic", "lesson"}:
        return True
    return False


def _is_generic_quiz_query(query: str) -> bool:
    q = (query or "").strip().lower()
    if not q:
        return True
    generic_phrases = {
        "quiz",
        "start quiz",
        "take quiz",
        "quiz me",
        "test me",
        "give me a quiz",
        "give me a test",
    }
    if q in generic_phrases:
        return True
    if len(q.split()) <= 2 and q in {"quiz", "test"}:
        return True
    return False


def _week_start_iso(dt: datetime) -> str:
    # Monday start-of-week in UTC.
    dt_utc = dt.astimezone(timezone.utc)
    monday = (dt_utc - timedelta(days=dt_utc.weekday())).date()
    return monday.isoformat()


def _render_chat_history(history: Optional[list[ChatTurn]], max_turns: int = 12) -> str:
    if not history:
        return ""
    trimmed = history[-max_turns:]
    lines: list[str] = []
    for turn in trimmed:
        role = (turn.role or "").strip().lower()
        if role not in {"user", "ai", "assistant"}:
            role = "user"
        speaker = "User" if role == "user" else "Tutor"
        content = (turn.content or "").strip()
        if not content:
            continue
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def _get_retriever_for_course(course_id: Optional[int]):
    if course_id is None:
        return retriever
    course_dir = os.path.join("db_chroma", f"course_{course_id}")
    os.makedirs(course_dir, exist_ok=True)
    course_store = Chroma(
        persist_directory=course_dir,
        embedding_function=embedding_function,
    )
    return course_store.as_retriever()


def _assert_course_owner(course_id: int, student_id: int) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_student_id FROM courses WHERE id = ?", (course_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Course not found")
    owner = row[0]
    # For legacy rows where owner is null, allow access.
    if owner is not None and int(owner) != int(student_id):
        raise HTTPException(status_code=403, detail="Forbidden")


# -------------------------------------------------
# 8. Teaching Endpoint
# -------------------------------------------------
# -------------------------------------------------
# 8. ADAPTIVE Teaching Endpoint
# -------------------------------------------------
@app.post("/teach")
async def teach_topic(request: QuestionRequest, current_student_id: Optional[int] = Depends(get_current_user)):
    try:
        # If token provided, trust it over body.
        if current_student_id is not None:
            request.student_id = current_student_id

        # If the user didn't pick a chapter/topic yet, guide them using the stored curriculum.
        if request.course_id is not None and _is_generic_teach_query(request.query) and not (request.active_topic or "").strip():
            rows = get_course_topics(int(request.course_id))
            chapter_titles: list[str] = []
            seen: set[str] = set()
            for r in rows:
                t = str(r.get("title") or "").strip()
                if not t or t in seen:
                    continue
                seen.add(t)
                chapter_titles.append(t)

            if not chapter_titles:
                return {
                    "answer": "I don't have a curriculum for this course yet. Upload the curriculum PDF and click 'Parse curriculum' first.",
                    "level": "",  # keep response shape stable
                }

            preview = "\n".join([f"- {t}" for t in chapter_titles[:10]])
            return {
                "answer": "Tell me which chapter/topic you want to learn today (or click 'Start lesson' from the curriculum list). Here are the first chapters I found:\n\n"
                + preview,
                "level": "",
            }

        selected_retriever = _get_retriever_for_course(request.course_id)

        # 1. Check Student Mastery Level
        mastery_score = get_student_mastery(request.student_id)

        # 2. Adjust Teaching Style based on Mastery
        teaching_style = "Explain simply using analogies."
        if mastery_score > 70:
            teaching_style = "Explain in depth with technical details."

        print(f"Student Mastery: {mastery_score}%. Mode: {teaching_style}") # Debug log

        history_text = _render_chat_history(request.chat_history)
        active_topic = (request.active_topic or "").strip()

        # If the user sends a generic request but they have an active topic, teach that.
        retrieval_query = request.query
        if _is_generic_teach_query(request.query) and active_topic:
            retrieval_query = active_topic

        # Enforce course-grounding: use ONLY retrieved context.
        adaptive_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are an AI Tutor for the current course. "
                    f"Teaching style: {teaching_style}.\n\n"
                    "Rules:\n"
                    "- Answer ONLY using the provided Context from the course materials.\n"
                    "- If the answer isn't in the Context, say: 'This topic is not covered in the course material.'\n"
                    "- Stay on the selected chapter/topic when provided.\n\n"
                    "Selected topic (if any): {active_topic}\n\n"
                    "Conversation so far (for this session):\n{history_text}\n\n"
                    "Context:\n{context}",
                ),
                ("human", "{input}"),
            ]
        )

        # Retrieve context using the course retriever.
        docs = []
        try:
            # langchain retrievers often expose this
            docs = selected_retriever.get_relevant_documents(retrieval_query)  # type: ignore[attr-defined]
        except Exception:
            try:
                docs = selected_retriever.invoke(retrieval_query)  # type: ignore[call-arg]
            except Exception:
                docs = []

        context = format_docs(docs) if docs else ""

        chain = adaptive_prompt | llm | StrOutputParser()
        response = chain.invoke(
            {
                "context": context,
                "input": request.query,
                "active_topic": active_topic,
                "history_text": history_text,
            }
        )
        return {"answer": response, "level": teaching_style}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------
# 9. UPGRADED: Quiz Endpoint
# -------------------------------------------------
@app.post("/quiz")
async def generate_quiz(request: QuestionRequest, current_student_id: Optional[int] = Depends(get_current_user)):
    try:
        if current_student_id is not None:
            request.student_id = current_student_id

        # Returns a JSON object: { "question": "...", "options": [...], "correct_answer": 1 }
        if request.course_id is None:
            return quiz_chain.invoke(request.query)

        selected_retriever = _get_retriever_for_course(request.course_id)

        history_text = _render_chat_history(request.chat_history)
        active_topic = (request.active_topic or "").strip()

        quiz_topic = request.query
        if _is_generic_quiz_query(quiz_topic) and active_topic:
            quiz_topic = active_topic

        # Retrieve context using the course retriever.
        docs = []
        try:
            docs = selected_retriever.get_relevant_documents(quiz_topic)  # type: ignore[attr-defined]
        except Exception:
            try:
                docs = selected_retriever.invoke(quiz_topic)  # type: ignore[call-arg]
            except Exception:
                docs = []

        if not docs:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No relevant course context found for quiz generation. "
                    "Upload content PDFs and click 'Ingest content', then pick a chapter/topic."
                ),
            )

        context = format_docs(docs)
        # Keep the prompt strict; history is captured via topic selection and context.
        _ = history_text  # reserved for future improvements

        chain = quiz_prompt_template | llm | JsonOutputParser()
        return chain.invoke({"context": context, "input": quiz_topic})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------
# 14.1 NEW: Course status endpoint
# -------------------------------------------------
@app.get("/course/{course_id}/status")
async def get_course_status(course_id: int, current_student_id: Optional[int] = Depends(get_current_user)):
    student_id = _require_user_id(current_student_id)
    _assert_course_owner(course_id=course_id, student_id=student_id)

    topics = get_course_topics(course_id)
    has_curriculum = bool(topics)

    content_pdfs = _list_course_uploaded_pdfs(course_id=course_id, file_kind="content")
    has_content_files = len(content_pdfs) > 0

    chroma_sqlite = os.path.join("db_chroma", f"course_{course_id}", "chroma.sqlite3")
    has_vectors = os.path.exists(chroma_sqlite)

    return {
        "course_id": course_id,
        "has_curriculum": has_curriculum,
        "has_content_files": has_content_files,
        "content_file_count": len(content_pdfs),
        "has_vectors": has_vectors,
    }


# -------------------------------------------------
# 15. NEW: Dashboard + weekly cached career recommendation
# -------------------------------------------------
@app.get("/dashboard")
async def get_dashboard(current_student_id: Optional[int] = Depends(get_current_user)):
    student_id = _require_user_id(current_student_id)

    courses = list_courses_for_owner(student_id)

    # Attach lightweight readiness status to each course.
    enriched = []
    for c in courses:
        cid = int(c.get("id"))
        topics = get_course_topics(cid)
        chroma_sqlite = os.path.join("db_chroma", f"course_{cid}", "chroma.sqlite3")
        enriched.append(
            {
                **c,
                "has_curriculum": bool(topics),
                "has_vectors": os.path.exists(chroma_sqlite),
            }
        )

    # Weekly career recommendation cache.
    week_start = _week_start_iso(datetime.now(timezone.utc))
    cached = get_career_recommendation(student_id=student_id, week_start=week_start)
    if cached is None:
        titles = [str(c.get("title") or "").strip() for c in courses]
        titles = [t for t in titles if t]
        titles_text = ", ".join(titles) if titles else "(no courses yet)"

        rec_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a practical career coach. "
                    "Given the student's current course titles, suggest a realistic career direction. "
                    "Keep it concise and actionable. Provide:\n"
                    "1) Two possible career paths (name + one-line why)\n"
                    "2) Five next skills to learn\n"
                    "3) Three portfolio project ideas\n",
                ),
                ("human", "Course titles: {titles}"),
            ]
        )
        rec_chain = rec_prompt | llm | StrOutputParser()
        recommendation_text = rec_chain.invoke({"titles": titles_text})
        upsert_career_recommendation(
            student_id=student_id,
            week_start=week_start,
            recommendation=recommendation_text,
        )
        cached = {
            "student_id": student_id,
            "week_start": week_start,
            "recommendation": recommendation_text,
        }

    return {
        "student_id": student_id,
        "course_count": len(courses),
        "courses": enriched,
        "career_recommendation": cached,
    }


# -------------------------------------------------
# 13. NEW: Ingest vectors for a course
# -------------------------------------------------
# Test instructions:
# 1) POST /ingest_vectors with {"course_id":1,"filepaths":["./uploads/<timestamp>_file.pdf"]}
# 2) POST /teach?course_id=1 with {"query":"Explain chapter 1"}
# -------------------------------------------------
@app.post("/ingest_vectors")
async def ingest_vectors(request: IngestVectorsRequest):
    try:
        filepaths = request.filepaths
        if not filepaths:
            filepaths = _list_course_uploaded_pdfs(course_id=request.course_id, file_kind="content")

        count = ingest_files_for_course(course_id=request.course_id, filepaths=filepaths)
        return {
            "status": "success",
            "course_id": request.course_id,
            "vector_count": count,
            "file_count": len(filepaths or []),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector ingestion failed: {str(e)}")


# -------------------------------------------------
# 13.1 NEW: Re-ingest vectors for a course (delete + rebuild)
# -------------------------------------------------
# Safety: requires confirm=true query param to delete.
@app.post("/reingest_course")
async def reingest_course(request: IngestVectorsRequest, confirm: bool = Query(False)):
    try:
        base_dir = os.path.abspath("db_chroma")
        course_dir = os.path.abspath(os.path.join("db_chroma", f"course_{request.course_id}"))

        # Safety check: ensure we only ever delete inside db_chroma
        if not (course_dir == base_dir or course_dir.startswith(base_dir + os.sep)):
            raise HTTPException(status_code=400, detail="Unsafe delete path computed; aborting.")

        exists = os.path.exists(course_dir)
        if not confirm:
            return {
                "status": "dry_run",
                "course_id": request.course_id,
                "course_dir": course_dir,
                "would_delete": bool(exists),
                "message": "Pass confirm=true to delete and re-ingest.",
            }

        if exists:
            shutil.rmtree(course_dir)

        filepaths = request.filepaths
        if not filepaths:
            filepaths = _list_course_uploaded_pdfs(course_id=request.course_id, file_kind="content")

        count = ingest_files_for_course(course_id=request.course_id, filepaths=filepaths)
        return {
            "status": "success",
            "course_id": request.course_id,
            "vector_count": count,
            "file_count": len(filepaths or []),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Re-ingest failed: {str(e)}")


# -------------------------------------------------
# 14. NEW: Next topic recommendation
# -------------------------------------------------
@app.get("/course/{course_id}/topics")
async def get_course_topics_endpoint(course_id: int):
    try:
        topics = get_course_topics(course_id)
        return {"course_id": course_id, "topics": topics}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch course topics: {str(e)}")


@app.get("/course/{course_id}/next_topic")
async def get_next_topic(course_id: int, student_id: int = Query(...)):
    try:
        curriculum_rows = get_course_topics(course_id)
        if not curriculum_rows:
            raise HTTPException(status_code=404, detail=f"No curriculum found for course_id={course_id}")

        # Build ordered list of (topic_order, topic_text)
        ordered_topics: list[tuple[int, str]] = []
        for row in curriculum_rows:
            try:
                order = int(row.get("topic_order"))
            except Exception:
                continue
            title = str(row.get("title") or "").strip()
            subtopic = row.get("subtopic")
            subtopic_text = str(subtopic).strip() if subtopic is not None else ""
            topic_text = subtopic_text or title
            if not topic_text:
                continue
            ordered_topics.append((order, topic_text))

        ordered_topics.sort(key=lambda x: x[0])
        if not ordered_topics:
            raise HTTPException(status_code=404, detail=f"No curriculum topics found for course_id={course_id}")

        # 1) Mastery from knowledge_state (if any)
        mastery_by_topic: dict[str, float] = {}
        ks_rows = get_knowledge_state(student_id=student_id, course_id=course_id)
        if ks_rows:
            for r in ks_rows:
                topic = str(r.get("topic") or "").strip()
                if not topic:
                    continue
                try:
                    mastery = float(r.get("mastery_score") or 0.0)
                except Exception:
                    mastery = 0.0
                mastery_by_topic[topic] = mastery

        # 2) Fill missing mastery using quiz_results averages (best-effort; quiz_results has no course_id)
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute(
                "SELECT topic, AVG(score) as avg_score FROM quiz_results WHERE student_id = ? GROUP BY topic",
                (student_id,),
            )
            quiz_avg = {str(row[0]): float(row[1]) for row in cur.fetchall() if row and row[0] is not None}
            conn.close()
        except Exception:
            quiz_avg = {}

        had_knowledge_state = bool(mastery_by_topic)

        # Decide next topic: lowest mastery among curriculum topics.
        best_topic = None
        best_order = None
        best_score = None

        for order, topic_text in ordered_topics:
            score = None
            if topic_text in mastery_by_topic:
                score = mastery_by_topic[topic_text]
            elif topic_text in quiz_avg:
                score = quiz_avg[topic_text]
            else:
                # No data -> treat as 0 mastery
                score = 0.0

            if best_score is None or score < best_score:
                best_score = score
                best_topic = topic_text
                best_order = order

        # If no knowledge_state at all and no quiz results for curriculum topics, return first topic.
        if not had_knowledge_state and not any(t in quiz_avg for _, t in ordered_topics):
            first_order, first_topic = ordered_topics[0]
            return {
                "next_topic": first_topic,
                "topic_order": first_order,
                "reason": "first_topic",
            }

        return {
            "next_topic": best_topic,
            "topic_order": best_order,
            "reason": "lowest_mastery" if had_knowledge_state else "lowest_quiz_avg",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Next topic selection failed: {str(e)}")


# -------------------------------------------------
# 10. NEW: Grade Endpoint
# -------------------------------------------------
class GradeRequest(BaseModel):
    student_id: int
    course_id: int = 1
    topic: str
    question: str
    student_answer: str
    correct_answer: str

@app.post("/grade")
async def grade_quiz(request: GradeRequest, current_student_id: Optional[int] = Depends(get_current_user)):
    try:
        if current_student_id is not None:
            request.student_id = current_student_id

        # 1. Ask AI for feedback
        feedback = grader_chain.invoke({
            "question": request.question,
            "student_answer": request.student_answer,
            "correct_answer": request.correct_answer
        })

        # 2. Calculate Score (Rule-Based Logic as requested)
        # If the feedback contains "Incorrect", score is 0. Else 100.
        # (In a real app, we'd make this smarter, but this satisfies the requirement)
        score = 0
        if "incorrect" not in feedback.lower():
            score = 100

        # 3. SAVE TO MEMORY (The "Knowledge Tracing")
        save_quiz_result(
            student_id=request.student_id,
            topic=request.topic,
            score=score,
            feedback=feedback
        )

        # 4. Update knowledge_state (attempts + incremental mean mastery)
        existing = get_knowledge_state_entry(
            student_id=request.student_id,
            course_id=request.course_id,
            topic=request.topic,
        )

        if existing:
            prev_mastery = float(existing.get("mastery_score") or 0.0)
            prev_attempts = int(existing.get("attempts") or 0)

            new_mastery = (prev_mastery * prev_attempts + score) / (prev_attempts + 1)
            new_attempts = prev_attempts + 1

            update_knowledge_state(
                student_id=request.student_id,
                course_id=request.course_id,
                topic=request.topic,
                mastery_score=new_mastery,
                attempts=new_attempts,
                notes=feedback,
            )
        else:
            update_knowledge_state(
                student_id=request.student_id,
                course_id=request.course_id,
                topic=request.topic,
                mastery_score=float(score),
                attempts=1,
                notes=feedback,
            )

        return {
            "feedback": feedback,
            "score": score,
            "mastery_update": "Student memory updated."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Setup Password Hashing
# NOTE: We intentionally avoid bcrypt here because some bcrypt/passlib combinations
# can fail at runtime on Windows environments. pbkdf2_sha256 is pure-python and stable.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    # Basic sanity bound; protects against absurd payloads.
    if password is None:
        raise HTTPException(status_code=400, detail="Password required")
    if len(password) > 512:
        raise HTTPException(status_code=400, detail="Password too long")
    return pwd_context.hash(password)

# -------------------------------------------------
# AUTH: Signup/Login (MVP, no password yet)
# -------------------------------------------------
class SignupRequest(BaseModel):
    username: str
    password: str  # Added password
    learning_style: str = "visual"

class LoginRequest(BaseModel):
    username: str
    password: str # Added password

@app.post("/auth/signup")
async def auth_signup(request: SignupRequest):
    try:
        username = request.username.strip()
        if not username or not request.password:
            raise HTTPException(status_code=400, detail="Username and password required")

        existing = get_student_by_username(username)
        if existing:
            raise HTTPException(status_code=400, detail="Username already exists")

        # Hash the password before saving
        hashed_pw = get_password_hash(request.password)

        try:
            # Pass hashed password to DB
            student_id = create_student(username=username, password_hash=hashed_pw, learning_style=request.learning_style)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create student: {str(e)}")

        token = _create_access_token(student_id)
        return {"access_token": token, "student_id": student_id}
    except HTTPException:
        raise


@app.post("/auth/login")
async def auth_login(request: LoginRequest):
    try:
        student = get_student_by_username(request.username)
        if not student:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Verify Password
        if not verify_password(request.password, student["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid credentials")

        student_id = int(student["id"])
        token = _create_access_token(student_id)
        return {"access_token": token, "student_id": student_id}
    except HTTPException:
        raise
# -------------------------------------------------
# 11. NEW: File Upload Endpoint
# -------------------------------------------------
# Unit test instructions:
# 1. Run: uvicorn main:app --reload
# 2. Test with curl:
#    curl -F "course_id=1" -F "file=@/path/to/kech101.pdf" http://127.0.0.1:8000/upload_file
# -------------------------------------------------
@app.post("/upload_file")
async def upload_file(
    course_id: int = Form(...),
    file_kind: str = Form("content"),
    file: UploadFile = File(...)
):
    try:
        # Generate unique filename with timestamp
        timestamp = int(time.time())
        safe_filename = f"{timestamp}_{file.filename}"

        target_dir = _course_upload_dir(course_id, file_kind)
        os.makedirs(target_dir, exist_ok=True)
        file_path = os.path.join(target_dir, safe_filename)

        # Save the file to disk
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        return {
            "saved_path": _normalize_path_for_api(file_path),
            "filename": file.filename,
            "course_id": course_id,
            "file_kind": (file_kind or "content").strip().lower(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


# -------------------------------------------------
# 12. NEW: Curriculum Parsing Endpoint
# -------------------------------------------------
# Test instructions:
# POST http://127.0.0.1:8000/parse_curriculum
# Body JSON: {"saved_path":"uploads/...", "course_id":1, "parse_mode":"toc"}
# -------------------------------------------------
class ParseCurriculumRequest(BaseModel):
    course_id: int
    saved_path: Optional[str] = None
    parse_mode: Optional[str] = "full"  # kept for backward-compat; curriculum parsing is LLM-only


def _resolve_saved_path(saved_path: str) -> str:
    if os.path.isabs(saved_path) and os.path.exists(saved_path):
        return saved_path

    backend_dir = os.path.dirname(__file__)
    candidate = os.path.abspath(os.path.join(backend_dir, saved_path))
    if os.path.exists(candidate):
        return candidate

    # Fallback: treat it as relative to the current working directory
    return os.path.abspath(saved_path)


def _chunk_text_best_effort(text: str, approx_tokens: int = 2000) -> list[str]:
    # Rough heuristic: ~4 chars per token for English.
    chunk_chars = max(1000, approx_tokens * 4)
    chunks: list[str] = []
    i = 0
    while i < len(text):
        chunk = text[i : i + chunk_chars]
        chunks.append(chunk)
        i += chunk_chars
    return chunks


def _extract_json_object_best_effort(raw_text: str) -> Any:
    raw_text = (raw_text or "").strip()

    # Direct parse first
    try:
        return json.loads(raw_text)
    except Exception:
        pass

    # Strip ```json fences if present
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw_text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return json.loads(fenced.group(1))

    # Fallback: parse the first {...} block
    start = raw_text.find("{")
    end = raw_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(raw_text[start : end + 1])

    raise ValueError("No JSON object found in LLM response")


@app.post("/parse_curriculum")
async def parse_curriculum(request: ParseCurriculumRequest):
    try:
        # Import locally so existing endpoints keep working even if dependency is missing.
        try:
            from PyPDF2 import PdfReader
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"PyPDF2 is required to parse PDFs: {str(e)}")

        if request.saved_path:
            pdf_path = _resolve_saved_path(request.saved_path)
            if not os.path.exists(pdf_path):
                raise HTTPException(status_code=400, detail=f"File not found: {pdf_path}")
        else:
            latest = _latest_course_uploaded_pdf(course_id=request.course_id, file_kind="curriculum")
            if not latest:
                raise HTTPException(
                    status_code=400,
                    detail="No curriculum PDF uploaded yet. Upload with file_kind='curriculum' first.",
                )
            pdf_path = latest

        source_file = os.path.basename(pdf_path)

        # Curriculum parsing is LLM-only: we do NOT do heuristic TOC/manual parsing.
        parse_mode = "full"

        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)

        # Extract all pages, then chunk best-effort.
        extracted_text_parts: list[str] = []
        for i in range(total_pages):
            extracted_text_parts.append(reader.pages[i].extract_text() or "")
        extracted_text = "\n\n".join(extracted_text_parts).strip()

        if not extracted_text:
            raise HTTPException(status_code=500, detail="No extractable text found in PDF.")

        chunks = _chunk_text_best_effort(extracted_text, approx_tokens=2000)

        # Keep prompt context within a reasonable size (best-effort safety)
        max_context_chars = 150000
        context_text = ""
        for chunk in chunks:
            if len(context_text) + len(chunk) + 2 > max_context_chars:
                break
            context_text += chunk + "\n\n"

        curriculum_system_prompt = (
            "You are a curriculum extraction agent. "
            "You MUST return valid JSON only (no Markdown, no commentary, no code fences). "
            "Use ONLY the provided PDF text. If details are unknown, make best-effort guesses but keep them plausible. "
            "Return JSON with this EXACT schema and key names:\n"
            "{{\n"
            "  \"course_title\": \"string\",\n"
            "  \"source_file\": \"<filename>\",\n"
            "  \"chapters\": [\n"
            "    {{\n"
            "      \"chapter_title\": \"string\",\n"
            "      \"chapter_order\": 1,\n"
            "      \"page_start\": 5,\n"
            "      \"page_end\": 12,\n"
            "      \"topics\": [\"t1\", \"t2\"],\n"
            "      \"learning_objectives\": [\"objective 1\", \"objective 2\"]\n"
            "    }}\n"
            "  ]\n"
            "}}\n"
            "Rules:\n"
            "- chapter_order must start at 1 and increment by 1.\n"
            "- page_start/page_end must be integers; if unknown, estimate.\n"
            "- topics and learning_objectives must be arrays (can be empty).\n"
            "- source_file must match the provided filename exactly."
        )

        curriculum_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", curriculum_system_prompt),
                (
                    "human",
                    "Filename: {source_file}\n"
                    "Parse mode: {parse_mode}\n"
                    "Total pages: {total_pages}\n\n"
                    "PDF text (may be truncated):\n"
                    "---\n"
                    "{context_text}\n"
                    "---\n\n"
                    "Return the JSON now."
                ),
            ]
        )

        curriculum_chain = curriculum_prompt | llm | StrOutputParser()
        raw_llm_text = curriculum_chain.invoke(
            {
                "source_file": source_file,
                "parse_mode": parse_mode,
                "total_pages": total_pages,
                "context_text": context_text,
            }
        )

        try:
            parsed = _extract_json_object_best_effort(raw_llm_text)
        except Exception:
            raise HTTPException(
                status_code=500,
                detail={
                    "error": "Failed to parse JSON from LLM output.",
                    "raw_llm_text": raw_llm_text,
                },
            )

        # Persist curriculum into DB (chapter row + optional topic rows)
        chapters = parsed.get("chapters", []) if isinstance(parsed, dict) else []
        topic_order = 1
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            chapter_title = str(ch.get("chapter_title", "")).strip() or "Untitled Chapter"
            page_start = ch.get("page_start")
            try:
                page_number = int(page_start) if page_start is not None else None
            except Exception:
                page_number = None

            save_curriculum_topic(
                course_id=request.course_id,
                topic_order=topic_order,
                title=chapter_title,
                subtopic=None,
                source_file=source_file,
                page_number=page_number,
            )
            topic_order += 1

            topics = ch.get("topics", [])
            if isinstance(topics, list):
                for t in topics:
                    topic_text = str(t).strip()
                    if not topic_text:
                        continue
                    save_curriculum_topic(
                        course_id=request.course_id,
                        topic_order=topic_order,
                        title=chapter_title,
                        subtopic=topic_text,
                        source_file=source_file,
                        page_number=page_number,
                    )
                    topic_order += 1

        return parsed

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Curriculum parsing failed: {str(e)}")


# -------------------------------------------------
# Run with:
# uvicorn main:app --reload
# -------------------------------------------------
