#!/usr/bin/env python3
import os

print("=== ServeApertusOn2Gpus.py — STREAMING + RAG EDITION v1.0 ===")

# ============================================================
# Environment setup
# ============================================================

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import uuid
import json as _json
import time
import threading
from typing import List, Literal

import torch
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TextIteratorStreamer,
)

# --- RAG imports --------------------------------------------------------
import lancedb
from sentence_transformers import SentenceTransformer

# ============================================================
# FastAPI app
# ============================================================

app = FastAPI()

# ============================================================
# Model config
# ============================================================

DEFAULT_MODEL_DIR = os.path.expanduser(
    "~/models/Apertus-8B-Instruct-2509"
)
MODEL_DIR = os.environ.get("APERTUS_MODEL_DIR", DEFAULT_MODEL_DIR)

print(f"[apertus] Using model dir: {MODEL_DIR}")

num_gpus = torch.cuda.device_count()
print(f"[apertus] torch.cuda.device_count() = {num_gpus}")

if num_gpus < 2:
    print("[apertus][WARN] Less than 2 GPUs visible — device_map='auto' will still use all available GPUs.")

print(f"[apertus] Loading tokenizer…")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_DIR,
    trust_remote_code=True,
    local_files_only=True,
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
tokenizer.padding_side = "left"

print(f"[apertus] Loading model… this may take a minute.")

model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    device_map="auto",          # use all visible GPUs
    torch_dtype=torch.bfloat16, # A100 → ideal
    low_cpu_mem_usage=True,
    trust_remote_code=True,
    local_files_only=True,
)

model.eval()
print("[apertus] Model loaded & ready!")

# ============================================================
# RAG config + state
# ============================================================

EMBED_DB_URI = os.environ.get("EMBEDDING_DB_URI", os.path.expanduser("~/EmbeddingsDB"))
EMBED_TABLE_NAME = os.environ.get("EMBEDDING_TABLE_NAME", "pdf_chunks")
EMBED_MODEL_NAME = os.environ.get(
    "EMBEDDING_MODEL_PATH",
    "sentence-transformers/all-MiniLM-L6-v2",
)
RAG_TOP_K = int(os.environ.get("RAG_TOP_K", 5))
RAG_MAX_CHARS = int(os.environ.get("RAG_MAX_CHARS", 16000))
RAG_DEBUG = int(os.environ.get("RAG_DEBUG", 1))

_RAG_ENABLED = False
_RAG_TABLE = None
_RAG_EMBED_MODEL = None


def init_rag():
    """
    Initialize LanceDB + embedding model.
    If anything fails, we just disable RAG and keep the normal chat working.
    """
    global _RAG_ENABLED, _RAG_TABLE, _RAG_EMBED_MODEL

    try:
        print(f"[RAG] Connecting to LanceDB at '{EMBED_DB_URI}'...")
        db = lancedb.connect(EMBED_DB_URI)

        if EMBED_TABLE_NAME not in db.table_names():
            print(f"[RAG] Table '{EMBED_TABLE_NAME}' not found. RAG disabled.")
            _RAG_ENABLED = False
            return

        _RAG_TABLE = db.open_table(EMBED_TABLE_NAME)
        print(f"[RAG] Opened table '{EMBED_TABLE_NAME}' with {_RAG_TABLE.count_rows()} rows.")

        print(f"[RAG] Loading embedding model: {EMBED_MODEL_NAME}")
        _RAG_EMBED_MODEL = SentenceTransformer(EMBED_MODEL_NAME)
        dim = _RAG_EMBED_MODEL.get_sentence_embedding_dimension()
        print(f"[RAG] Embedding dimension: {dim}")

        _RAG_ENABLED = True
        print("[RAG] Retrieval is ENABLED.")
    except Exception as e:
        print(f"[RAG] Init failed: {e}")
        print("[RAG] Retrieval is DISABLED.")
        _RAG_ENABLED = False
        _RAG_TABLE = None
        _RAG_EMBED_MODEL = None


def retrieve_context(query: str,
                     top_k: int = RAG_TOP_K,
                     max_chars: int = RAG_MAX_CHARS):
    """
    Retrieve relevant context from LanceDB for a given query.
    Returns (concatenated_text, hits_list) where hits_list is a list of dicts:
      { "doc_id": str, "page": int|str, "text": str }
    If RAG is disabled/empty, returns ("", []).
    """
    if not _RAG_ENABLED or _RAG_TABLE is None or _RAG_EMBED_MODEL is None:
        return "", []

    query = query.strip()
    if not query:
        return "", []

    try:
        q_vec = _RAG_EMBED_MODEL.encode([query])[0].astype("float32").tolist()
        hits = _RAG_TABLE.search(q_vec).limit(top_k).to_list()

        if not hits:
            if RAG_DEBUG:
                print("[RAG] No hits.")
            return "", []

        pieces = []
        total_chars = 0
        hits_export = []

        print(f"[RAG] Retrieved {len(hits)} candidate chunk(s).")

        for idx, h in enumerate(hits):
            doc_id = str(h.get("doc_id", "unknown"))
            page = h.get("page", "?")
            text = str(h.get("text", ""))

            prefix = f"[{doc_id} p.{page}] "
            snippet = prefix + text

            # store a clean version for the client UI
            hits_export.append({
                "doc_id": doc_id,
                "page": page,
                "text": text,
            })

            if total_chars + len(snippet) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 0:
                    pieces.append(snippet[:remaining])
                print(f"[RAG] Reached max_chars={max_chars}, truncating context.")
                break

            pieces.append(snippet)
            total_chars += len(snippet)

            if RAG_DEBUG >= 1:
                preview = text[:200].replace("\n", " ")
                print(
                    f"[RAG]  -> hit {idx}: {doc_id} p.{page} "
                    f"(chunk len={len(text)}) preview='{preview}...'"
                )

        return "\n\n".join(pieces), hits_export

    except Exception as e:
        print(f"[RAG] Retrieval error: {e}")
        return "", []

# init RAG once, after model is loaded
init_rag()

# ============================================================
# Request/Response models
# ============================================================

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95
    stream: bool = False


class ChatRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95


class ChatResponse(BaseModel):
    response: str


# ============================================================
# Prompt builder (unchanged)
# ============================================================

def build_prompt(messages: List[ChatMessage]) -> str:
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    return tokenizer.apply_chat_template(
        msg_dicts,
        tokenize=False,
        add_generation_prompt=True,
    )


# ============================================================
# Helper: inject RAG context into last user message
# ============================================================

def apply_rag_to_messages(messages: List[ChatMessage]):
    """
    Find the *last* user message, retrieve context for it, and rewrite its content
    to include the retrieved context + the original question.

    Returns:
      (new_messages, rag_hits_list, rag_user_message_text)

    rag_hits_list is [] and rag_user_message_text is None if RAG is disabled or nothing found.
    """
    if not _RAG_ENABLED:
        if RAG_DEBUG:
            print("[RAG] Disabled or unavailable, skipping injection.")
        return messages, [], None

    # find last user message index
    last_user_idx = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "user":
            last_user_idx = i
            break

    if last_user_idx is None:
        return messages, [], None

    orig_user = messages[last_user_idx]
    user_text = orig_user.content

    ctx, hits = retrieve_context(user_text)
    if not ctx:
        if RAG_DEBUG:
            print("[RAG] No context retrieved for this query.")
        return messages, [], None

    print("[RAG] Injecting context into last user message.")

    new_user_content = (
        "Benutze den folgenden Kontext, bzw. die folgenden Informationen um die Fragen der Nutzer*innen zu beantworten, wenn diese zur Frage passen:\n\n"
        f"{ctx}\n\n"
        f"User question:\n{user_text}"
    )

    new_msgs = list(messages)
    new_msgs[last_user_idx] = ChatMessage(role="user", content=new_user_content)
    return new_msgs, hits, new_user_content


# ============================================================
# Simple non-streaming endpoint (optional RAG for /chat)
# ============================================================

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    messages = [ChatMessage(role="user", content=req.prompt)]
    messages, _rag_hits, _rag_user_message = apply_rag_to_messages(messages)

    prompt = build_prompt(messages)
    inputs = tokenizer(prompt, return_tensors="pt").to("cuda:0")

    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=req.max_new_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            do_sample=True,
        )

    new_tokens = out[0][inputs.input_ids.shape[1]:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    return ChatResponse(response=text)



# ============================================================
# Fully streaming OpenAI-compatible endpoint WITH RAG
# ============================================================

@app.post("/v1/chat/completions")
async def v1_chat_completions(req: ChatCompletionRequest):

    # 1) apply RAG to messages
    rag_messages, rag_hits, rag_user_message = apply_rag_to_messages(req.messages)

    # 2) build prompt from RAG-augmented messages
    prompt = build_prompt(rag_messages)

    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        add_special_tokens=False,
    ).to("cuda:0")

    # ============================================================
    # NON-STREAMING path
    # ============================================================
    if not req.stream:
        with torch.no_grad():
            out = model.generate(
                **inputs,
                max_new_tokens=req.max_tokens,
                do_sample=True,
                temperature=req.temperature,
                top_p=req.top_p,
            )

        prompt_len = inputs.input_ids.shape[1]
        new_ids = out[0][prompt_len:]
        text = tokenizer.decode(new_ids, skip_special_tokens=True)

        cid = f"chatcmpl-{uuid.uuid4().hex}"
        return {
            "id": cid,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop"
            }],
            # extra transparency for your UI
            "rag_hits": rag_hits,
            "rag_user_message": rag_user_message,
        }

    # ============================================================
    # TRUE STREAMING path — send RAG meta first, then tokens
    # ============================================================

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_special_tokens=True,
        skip_prompt=True,
    )

    def generate():
        with torch.no_grad():
            model.generate(
                **inputs,
                max_new_tokens=req.max_tokens,
                do_sample=True,
                temperature=req.temperature,
                top_p=req.top_p,
                streamer=streamer,
            )

    thread = threading.Thread(target=generate)
    thread.start()

    cid = f"chatcmpl-{uuid.uuid4().hex}"

    async def event_stream():
        # 1) FIRST EVENT: RAG info + injected user message
        meta = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "delta": {},          # no tokens here
                "finish_reason": None
            }],
            "rag_hits": rag_hits,
            "rag_user_message": rag_user_message,
        }
        yield "data: " + _json.dumps(meta, ensure_ascii=False) + "\n\n"

        # 2) THEN: token-by-token stream
        first_token = True
        for token in streamer:
            if not token:
                continue

            delta = {"content": token}
            if first_token:
                delta["role"] = "assistant"
                first_token = False

            chunk = {
                "id": cid,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": req.model,
                "choices": [{
                    "index": 0,
                    "delta": delta,
                    "finish_reason": None
                }]
            }

            yield "data: " + _json.dumps(chunk, ensure_ascii=False) + "\n\n"

        # final chunk with finish_reason=stop
        final = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        }
        yield "data: " + _json.dumps(final, ensure_ascii=False) + "\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ============================================================
# Uvicorn launcher
# ============================================================

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("APERTUS_HOST", "0.0.0.0")
    port = int(os.environ.get("APERTUS_PORT", "9000"))
    print(f"[apertus] Launching streaming server on {host}:{port}")
    uvicorn.run(app, host=host, port=port, reload=False)