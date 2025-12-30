#!/usr/bin/env python3
import os

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoTokenizer, AutoModelForCausalLM

app = FastAPI()

DEFAULT_MODEL_DIR = os.path.expanduser(
    "~/models/apertus-70b-instruct-2509-unsloth-bnb-4bit"
)
MODEL_DIR = os.environ.get("APERTUS_MODEL_DIR", DEFAULT_MODEL_DIR)

print(f"[apertus] Using model dir: {MODEL_DIR}")

print(f"[apertus] Loading tokenizer via AutoTokenizer from: {MODEL_DIR}")
tokenizer = AutoTokenizer.from_pretrained(
    MODEL_DIR,
    local_files_only=True,
    trust_remote_code=True,
)

print(f"[apertus] Loading model from: {MODEL_DIR}")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    device_map={"": "cuda:0"},  # try pure GPU from the start
    torch_dtype="auto",
    low_cpu_mem_usage=True,
    trust_remote_code=True,
    local_files_only=True,
)

model.eval()
print("[apertus] Model loaded, ready.")

class ChatRequest(BaseModel):
    prompt: str
    max_new_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.95

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    messages = [{"role": "user", "content": req.prompt}]
    prompt = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    inputs = tokenizer(
        prompt,
        return_tensors="pt",
        add_special_tokens=False,
    ).to("cuda:0")

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=req.max_new_tokens,
            do_sample=True,
            temperature=req.temperature,
            top_p=req.top_p,
        )

    new_tokens = output_ids[0][inputs.input_ids.shape[1]:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    return ChatResponse(response=text)

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("APERTUS_HOST", "0.0.0.0")
    port = int(os.environ.get("APERTUS_PORT", "9000"))
    print(f"[apertus] Starting Uvicorn on {host}:{port}")
    uvicorn.run("serve_apertus:app", host=host, port=port, reload=False)
