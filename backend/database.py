import sqlite3
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

DB_PATH = "student_data.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cursor = conn.cursor()

    # Students (existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            learning_style TEXT DEFAULT 'visual'
        )
    ''')

    # Migration: add password_hash (and learning_style) columns if the table existed before.
    try:
        cursor.execute("PRAGMA table_info(students)")
        cols = {row[1] for row in cursor.fetchall()}
        if "password_hash" not in cols:
            cursor.execute("ALTER TABLE students ADD COLUMN password_hash TEXT")
        if "learning_style" not in cols:
            cursor.execute("ALTER TABLE students ADD COLUMN learning_style TEXT DEFAULT 'visual'")
    except Exception:
        # Best-effort migration.
        pass

    # Quiz Results (existing)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS quiz_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            topic TEXT,
            score INTEGER,
            feedback TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Courses (new)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            description TEXT,
            owner_student_id INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Curriculum topics (ordered list of topics/subtopics)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS curriculum_topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            topic_order INTEGER,
            title TEXT,
            subtopic TEXT,
            source_file TEXT,
            page_number INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Course material files (store metadata about uploaded PDFs)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER,
            filename TEXT,
            filepath TEXT,
            uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Knowledge state (per student per topic persistent state)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS knowledge_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            course_id INTEGER,
            topic TEXT,
            mastery_score REAL DEFAULT 0,
            attempts INTEGER DEFAULT 0,
            last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
    ''')

    # Weekly cached career recommendations (per student per week)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS career_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            week_start TEXT,
            recommendation TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, week_start)
        )
    ''')

    # Migration: add attempts column if the table existed before this field was introduced
    try:
        cursor.execute("PRAGMA table_info(knowledge_state)")
        cols = {row[1] for row in cursor.fetchall()}
        if "attempts" not in cols:
            cursor.execute("ALTER TABLE knowledge_state ADD COLUMN attempts INTEGER DEFAULT 0")
    except Exception:
        # Best-effort: if ALTER fails (e.g., table doesn't exist yet), ignore.
        pass

    conn.commit()
    conn.close()

# --- Existing helpers preserved ---

def save_quiz_result(student_id, topic, score, feedback):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO quiz_results (student_id, topic, score, feedback) VALUES (?, ?, ?, ?)",
        (student_id, topic, score, feedback)
    )
    conn.commit()
    conn.close()

def get_student_mastery(student_id) -> float:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT AVG(score) FROM quiz_results WHERE student_id = ?", (student_id,))
    result = cursor.fetchone()[0]
    conn.close()
    return result if result else 0.0


# Update create_student to accept password_hash
def create_student(username: str, password_hash: str, learning_style: str = "visual") -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO students (username, password_hash, learning_style) VALUES (?, ?, ?)",
        (username, password_hash, learning_style),
    )
    conn.commit()
    student_id = cursor.lastrowid
    conn.close()
    return student_id


def get_student_by_username(username: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM students WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

# --- New DB helper functions ---

def create_course(title: str, description: str = "", owner_student_id: Optional[int] = None) -> int:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO courses (title, description, owner_student_id) VALUES (?, ?, ?)",
                   (title, description, owner_student_id))
    conn.commit()
    course_id = cursor.lastrowid
    conn.close()
    return course_id

def list_courses() -> List[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_courses_for_owner(owner_student_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM courses WHERE owner_student_id = ? ORDER BY created_at DESC",
        (owner_student_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_course_file(course_id: int, filename: str, filepath: str):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO course_files (course_id, filename, filepath) VALUES (?, ?, ?)",
                   (course_id, filename, filepath))
    conn.commit()
    conn.close()

def save_curriculum_topic(course_id: int, topic_order: int, title: str, subtopic: Optional[str],
                          source_file: Optional[str], page_number: Optional[int]):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO curriculum_topics (course_id, topic_order, title, subtopic, source_file, page_number)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (course_id, topic_order, title, subtopic, source_file, page_number))
    conn.commit()
    conn.close()

def get_course_topics(course_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM curriculum_topics WHERE course_id = ? ORDER BY topic_order", (course_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_knowledge_state_entry(student_id: int, course_id: int, topic: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM knowledge_state WHERE student_id = ? AND course_id = ? AND topic = ?",
        (student_id, course_id, topic),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def update_knowledge_state(
    student_id: int,
    course_id: int,
    topic: str,
    mastery_score: float,
    attempts: int = 0,
    notes: str = "",
):
    conn = get_conn()
    cursor = conn.cursor()
    # upsert style: update if exists else insert
    cursor.execute('''
        SELECT id FROM knowledge_state WHERE student_id = ? AND course_id = ? AND topic = ?
    ''', (student_id, course_id, topic))
    row = cursor.fetchone()
    if row:
        cursor.execute('''
            UPDATE knowledge_state
            SET mastery_score = ?, attempts = ?, last_updated = CURRENT_TIMESTAMP, notes = ?
            WHERE id = ?
        ''', (mastery_score, attempts, notes, row["id"]))
    else:
        cursor.execute('''
            INSERT INTO knowledge_state (student_id, course_id, topic, mastery_score, attempts, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (student_id, course_id, topic, mastery_score, attempts, notes))
    conn.commit()
    conn.close()

def get_knowledge_state(student_id: int, course_id: int) -> List[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM knowledge_state WHERE student_id = ? AND course_id = ?", (student_id, course_id))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_career_recommendation(student_id: int, week_start: str) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM career_recommendations WHERE student_id = ? AND week_start = ?",
        (student_id, week_start),
    )
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_career_recommendation(student_id: int, week_start: str, recommendation: str) -> None:
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO career_recommendations (student_id, week_start, recommendation)
        VALUES (?, ?, ?)
        ON CONFLICT(student_id, week_start)
        DO UPDATE SET recommendation = excluded.recommendation, created_at = CURRENT_TIMESTAMP
        """,
        (student_id, week_start, recommendation),
    )
    conn.commit()
    conn.close()

# initialize DB on import
init_db()
