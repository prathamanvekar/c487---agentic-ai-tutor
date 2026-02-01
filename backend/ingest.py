import os
from typing import List
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma

# 1. Load environment variables
load_dotenv()


def _resolve_path(path: str) -> str:
    if os.path.isabs(path) and os.path.exists(path):
        return path
    return os.path.abspath(path)


def ingest_files_for_course(course_id: int, filepaths: List[str]) -> int:
    """Ingest one or more PDFs into a course-specific Chroma vector store.

    - Splits PDF text into chunks using RecursiveCharacterTextSplitter
    - Embeds using HuggingFaceEmbeddings
    - Persists into ./db_chroma/course_<course_id>
    - Returns count of vectors stored (best-effort: number of chunks added)
    """

    if not isinstance(course_id, int):
        raise ValueError("course_id must be an int")
    if not filepaths:
        return 0

    course_db_path = os.path.join("db_chroma", f"course_{course_id}")
    os.makedirs(course_db_path, exist_ok=True)

    # Load + chunk
    all_chunks = []
    for fp in filepaths:
        resolved = _resolve_path(fp)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"File not found: {resolved}")
        loader = PyPDFLoader(resolved)
        documents = loader.load()

        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_documents(documents)

        # Attach metadata for debugging/filtering
        for d in chunks:
            d.metadata = d.metadata or {}
            d.metadata.update({"course_id": course_id, "source": os.path.basename(resolved), "path": resolved})
        all_chunks.extend(chunks)

    if not all_chunks:
        return 0

    # Embed + persist
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    vector_store = Chroma(
        persist_directory=course_db_path,
        embedding_function=embeddings,
    )

    try:
        ids = vector_store.add_documents(all_chunks)
        stored_count = len(ids) if ids else len(all_chunks)
    except Exception:
        # Fallback for older APIs
        Chroma.from_documents(documents=all_chunks, embedding=embeddings, persist_directory=course_db_path)
        stored_count = len(all_chunks)

    # Best-effort persist (API varies by version)
    try:
        vector_store.persist()  # type: ignore[attr-defined]
    except Exception:
        pass

    return stored_count

def ingest_documents():
    # Define paths
    pdf_path = "data/course_material.pdf"  # Ensure this file exists!
    db_path = "db_chroma"

    print(f"Loading {pdf_path}...")

    # 2. Load the PDF
    if not os.path.exists(pdf_path):
        print(f"Error: File not found at {pdf_path}")
        return

    loader = PyPDFLoader(pdf_path)
    documents = loader.load()

    # 3. Split the PDF (Chunking)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documents)

    print(f"Split into {len(chunks)} chunks.")

    # 4. Create Embeddings (Using Free HuggingFace model)
    print("Initializing HuggingFace Embeddings (this might take a moment first time)...")
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")

    # 5. Store in Vector DB
    print("Saving to ChromaDB...")
    vector_store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=db_path
    )

    print(f"Ingestion complete! Database created at ./{db_path}")

if __name__ == "__main__":
    ingest_documents()
