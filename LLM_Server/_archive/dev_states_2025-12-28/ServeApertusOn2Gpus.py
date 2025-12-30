#!/usr/bin/env python3
import os

print("=== ServeApertusOn2Gpus.py — STREAMING EDITION v1.0 ===")

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

# ============================================================
# FastAPI app
# ============================================================

app = FastAPI()

# ============================================================
# Model config
# ============================================================

DEFAULT_MODEL_DIR = os.path.expanduser(
    "~/models/apertus-70b-instruct-2509-unsloth-bnb-4bit"
)
MODEL_DIR = os.environ.get("APERTUS_MODEL_DIR", DEFAULT_MODEL_DIR)

print(f"[apertus] Using model dir: {MODEL_DIR}")

num_gpus = torch.cuda.device_count()
print(f"[apertus] torch.cuda.device_count() = {num_gpus}")

if num_gpus < 2:
    print("[apertus][WARN] Less than 2 GPUs visible — device_map='auto' will still use all available GPUs.")

# ============================================================
# Load tokenizer & model
# ============================================================

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
    device_map="auto",       # USE ALL GPUs
    torch_dtype="auto",
    low_cpu_mem_usage=True,
    trust_remote_code=True,
    local_files_only=True,
)

model.eval()
print("[apertus] Model loaded & ready!")

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
# Build prompt
# ============================================================

def build_prompt(messages: List[ChatMessage]) -> str:
    msg_dicts = [{"role": m.role, "content": m.content} for m in messages]
    return tokenizer.apply_chat_template(
        msg_dicts,
        tokenize=False,
        add_generation_prompt=True,
    )

# ============================================================
# Simple non-streaming endpoint
# ============================================================

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):

    messages = [{"role": "user", "content": req.prompt}]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )

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
# Fully streaming OpenAI-compatible endpoint
# ============================================================

@app.post("/v1/chat/completions")
async def v1_chat_completions(req: ChatCompletionRequest):

    prompt = build_prompt(req.messages)

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
            }]
        }

    # ============================================================
    # TRUE STREAMING path — token-by-token
    # ============================================================

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_special_tokens=True,
        skip_prompt=True,
    )

    # run generation in background thread
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

        first = True

        for token in streamer:

            if not token:
                continue

            delta = {"content": token}
            if first:
                delta["role"] = "assistant"
                first = False

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

        # final chunk
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
