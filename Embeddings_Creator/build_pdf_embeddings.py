#!/usr/bin/env python3
"""
build_pdf_embeddings.py

Build PDF text chunk embeddings and store them in LanceDB for RAG.

Defaults (repo-structure aligned):
- PDF input:  ~/FuzzyBot_HSBI/Embeddings_Creator/data/raw
- DB output:  ~/FuzzyBot_HSBI/LLM_Server/rag/db
- Table:      pdf_chunks
- Model:      sentence-transformers/all-MiniLM-L6-v2

Env overrides:
- FUZZYBOT_DB_DIR             -> base DB directory (preferred)
- EMBEDDING_DB_URI            -> LanceDB directory (overrides FUZZYBOT_DB_DIR)
- FUZZYBOT_PDF_DIR            -> PDF input directory (preferred)
- EMBEDDING_PDF_DIR           -> PDF input directory (fallback)
- EMBEDDING_TABLE_NAME        -> LanceDB table name (default: pdf_chunks)
- EMBEDDING_MODEL_PATH        -> embedding model (default: all-MiniLM-L6-v2)
- EMBEDDING_CHUNK_SIZE        -> chunk size in characters (default: 800)
- EMBEDDING_CHUNK_OVERLAP     -> overlap in characters (default: 200)
- EMBEDDING_MIN_CHARS         -> minimum chars per chunk (default: 100)
- EMBEDDING_BATCH_SIZE        -> batch size for encoding (default: 64)
- CLEAR_TABLE=1               -> drop/recreate table before ingest
"""

import os
import uuid
from pathlib import Path
from typing import List, Dict, Any

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import lancedb


# ---------------- PATHS (repo-aligned defaults) ---------------- #

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # .../FuzzyBot_HSBI

DEFAULT_DB_DIR = Path(
    os.environ.get("FUZZYBOT_DB_DIR", str(PROJECT_ROOT / "LLM_Server" / "rag" / "db"))
).expanduser()

DB_URI = Path(os.environ.get("EMBEDDING_DB_URI", str(DEFAULT_DB_DIR))).expanduser()

DEFAULT_PDF_DIR = Path(
    os.environ.get("FUZZYBOT_PDF_DIR", str(PROJECT_ROOT / "Embeddings_Creator" / "data" / "raw"))
).expanduser()

PDF_DIR = Path(os.environ.get("EMBEDDING_PDF_DIR", str(DEFAULT_PDF_DIR))).expanduser()

# ---------------- EMBEDDING CONFIG ---------------- #

TABLE_NAME = os.environ.get("EMBEDDING_TABLE_NAME", "pdf_chunks")

MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL_PATH",
    "sentence-transformers/all-MiniLM-L6-v2",
)

CHUNK_SIZE = int(os.environ.get("EMBEDDING_CHUNK_SIZE", 800))
CHUNK_OVERLAP = int(os.environ.get("EMBEDDING_CHUNK_OVERLAP", 200))
MIN_CHUNK_LEN = int(os.environ.get("EMBEDDING_MIN_CHARS", 100))
BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", 64))

CLEAR_TABLE = int(os.environ.get("CLEAR_TABLE", "0"))  # 1 = rebuild from scratch


# ---------------- HELPERS ---------------- #

def scan_pdfs(folder: Path) -> List[Path]:
    if not folder.exists():
        raise SystemExit(f"[ERROR] PDF input folder does not exist: {folder.resolve()}")
    pdfs = sorted(folder.rglob("*.pdf"))
    return pdfs


def extract_pdf_text(path: Path) -> List[Dict[str, Any]]:
    """Extract per-page text from a PDF."""
    reader = PdfReader(str(path))
    doc_id = path.name
    pages: List[Dict[str, Any]] = []

    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = txt.strip()
        if not txt:
            continue

        pages.append(
            {
                "doc_id": doc_id,
                "page": i + 1,
                "text": txt,
            }
        )
    return pages


def chunk_text(text: str) -> List[str]:
    """
    Simple character-based chunking with overlap.
    Uses whitespace normalization first.
    """
    text = " ".join(text.split())
    n = len(text)
    if n == 0:
        return []

    overlap = max(0, min(CHUNK_OVERLAP, CHUNK_SIZE - 1))
    step = max(1, CHUNK_SIZE - overlap)

    chunks: List[str] = []
    start = 0

    while start < n:
        end = min(start + CHUNK_SIZE, n)

        # Optional: try to end on a whitespace boundary for nicer chunks
        if end < n:
            last_space = text.rfind(" ", start + max(1, int(CHUNK_SIZE * 0.5)), end)
            if last_space != -1:
                end = last_space

        chunk = text[start:end].strip()
        if len(chunk) >= MIN_CHUNK_LEN:
            chunks.append(chunk)

        if end >= n:
            break

        start += step

    return chunks


def build_records_from_pdfs(pdf_paths: List[Path]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []

    for pdf_path in pdf_paths:
        print(f"[INFO] Processing PDF: {pdf_path}")
        pages = extract_pdf_text(pdf_path)

        for page in pages:
            chunks = chunk_text(page["text"])
            for chunk_idx, chunk in enumerate(chunks):
                records.append(
                    {
                        "id": str(uuid.uuid4()),
                        "doc_id": page["doc_id"],
                        "page": page["page"],
                        "chunk": chunk_idx,
                        "text": chunk,
                        # "vector" added later
                    }
                )

    print(f"[INFO] Total text chunks: {len(records)}")
    return records


def embed_records(records: List[Dict[str, Any]], model: SentenceTransformer) -> None:
    if not records:
        return

    print("[INFO] Computing embeddings...")
    texts = [r["text"] for r in records]

    for start in range(0, len(texts), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(texts))
        batch_texts = texts[start:end]

        embs = model.encode(
            batch_texts,
            batch_size=len(batch_texts),
            show_progress_bar=False,
            convert_to_numpy=True,
        )

        for i, emb in enumerate(embs):
            records[start + i]["vector"] = emb.astype("float32").tolist()

        print(f"[INFO] Embedded {end}/{len(texts)} chunks")

    print("[INFO] Embeddings computed.")


def upsert_into_lancedb(records: List[Dict[str, Any]], db_uri: Path, table_name: str) -> None:
    if not records:
        print("[WARN] No records to store.")
        return

    db_uri = Path(db_uri).expanduser()
    db_uri.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Connecting to LanceDB at '{db_uri}'...")
    db = lancedb.connect(str(db_uri))

    if CLEAR_TABLE and table_name in db.table_names():
        print(f"[WARN] CLEAR_TABLE=1 -> dropping existing table '{table_name}'")
        db.drop_table(table_name)

    if table_name in db.table_names():
        print(f"[INFO] Appending to existing table '{table_name}'...")
        table = db.open_table(table_name)
        table.add(records)
    else:
        print(f"[INFO] Creating table '{table_name}'...")
        table = db.create_table(table_name, records)

    # Create/ensure vector index (best-effort)
    try:
        print("[INFO] Ensuring vector index on 'vector' column...")
        table.create_index("vector")
    except Exception as e:
        print(f"[WARN] Could not create index (non-fatal): {e}")

    try:
        count = table.count_rows()
    except Exception:
        count = "unknown"

    print("[INFO] Done. Table row count:", count)


def main() -> None:
    print("[INFO] ------------ Embeddings Builder ------------")
    print(f"[INFO] PDF input folder: {PDF_DIR.resolve()}")
    print(f"[INFO] LanceDB folder:   {DB_URI.resolve()}")
    print(f"[INFO] Table name:       {TABLE_NAME}")
    print(f"[INFO] Model:            {MODEL_NAME}")
    print(f"[INFO] Chunk size:       {CHUNK_SIZE}")
    print(f"[INFO] Chunk overlap:    {CHUNK_OVERLAP}")
    print(f"[INFO] Min chunk chars:  {MIN_CHUNK_LEN}")
    print(f"[INFO] Batch size:       {BATCH_SIZE}")
    print(f"[INFO] CLEAR_TABLE:      {CLEAR_TABLE}")
    print("[INFO] -------------------------------------------")

    pdf_paths = scan_pdfs(PDF_DIR)
    if not pdf_paths:
        raise SystemExit(f"[ERROR] No PDFs found in: {PDF_DIR.resolve()}")

    print(f"[INFO] Found {len(pdf_paths)} PDF(s).")

    print("[INFO] Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)
    print(f"[INFO] Embedding dimension: {model.get_sentence_embedding_dimension()}")

    records = build_records_from_pdfs(pdf_paths)
    if not records:
        raise SystemExit("[ERROR] No text chunks extracted from PDFs.")

    embed_records(records, model)
    upsert_into_lancedb(records, DB_URI, TABLE_NAME)

    print("[INFO] Embedding build complete.")


if __name__ == "__main__":
    main()
