# RUNBOOK: Install and Place Files (Cluster + VM)

Version: 2025-12-28  
Purpose: Explain where each file lives and how to deploy the client and server.

## Overview

There are two deployment locations:

- Cluster (login + GPU nodes): model server + embeddings.
- Client VM: web UI + local proxy, exposed via Apache.

## Cluster install (login + GPU)

### 0) SSH into the cluster

```bash
ssh -i ~/.ssh/id_ed25519 <USER>@usr.yai.hsbi.de
```

Omit `-i ...` if an SSH key is not used.

### 1) Get or update the repo

Clone the repo (first time):

```bash
cd ~
git clone https://github.com/strangerattractor/FuzzyBot_HSBI.git
cd ~/FuzzyBot_HSBI
```

If it already exists, update it:

```bash
cd ~/FuzzyBot_HSBI
git status
git pull --rebase
```

If submodules are used:

```bash
cd ~/FuzzyBot_HSBI
git submodule update --init --recursive
```

### 2) Create or activate the Python environment (LLM server + embeddings)

Note: The VM proxy only needs Python + `requests`; it does not require this conda env.

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate fuzzybot
```

If the env does not exist yet, create it (recommended: requirements file):

```bash
conda create -n fuzzybot python=3.11 -y
conda activate fuzzybot
pip install -U pip wheel
pip install -r env/requirements-llm-server.txt
```

Alternative: conda environment file (creates the base env, then install deps):

```bash
conda env create -f env/conda-environment.yml -n fuzzybot
conda activate fuzzybot
pip install -U pip wheel
pip install -r env/requirements-llm-server.txt
```

### 3) Download the model

Use this model path (fast / scratch if available):

```bash
mkdir -p /scratch/$USER/fuzzybot_models
export FUZZYBOT_MODELS_DIR=/scratch/$USER/fuzzybot_models
```

If scratch is not available, use:

```bash
mkdir -p ~/models
export FUZZYBOT_MODELS_DIR=~/models
```

Model used in this project: `Apertus-8B-Instruct-2509`
(repo: `swiss-ai/Apertus-8B-Instruct-2509`).

Download via Hugging Face CLI (no git-lfs needed):

```bash
MODEL_NAME=Apertus-8B-Instruct-2509
MODEL_REPO=swiss-ai/${MODEL_NAME}
huggingface-cli download "$MODEL_REPO" \
  --local-dir "$FUZZYBOT_MODELS_DIR/$MODEL_NAME" \
  --local-dir-use-symlinks False
```

If the weights already exist on the cluster, copy them into
`$FUZZYBOT_MODELS_DIR/$MODEL_NAME` and skip the download.

Both repos are public at the time of writing (no HF login required).

Optional 4-bit variant (smaller GPUs):

```bash
MODEL_NAME=Apertus-8B-Instruct-2509-unsloth-bnb-4bit
MODEL_REPO=unsloth/${MODEL_NAME}
huggingface-cli download "$MODEL_REPO" \
  --local-dir "$FUZZYBOT_MODELS_DIR/$MODEL_NAME" \
  --local-dir-use-symlinks False
```

Point the server to the chosen model:

```bash
export FUZZYBOT_MODEL_NAME=Apertus-8B-Instruct-2509
```

If the 4-bit variant is preferred, swap both `MODEL_NAME` and `FUZZYBOT_MODEL_NAME`
to `Apertus-8B-Instruct-2509-unsloth-bnb-4bit` and download from
`unsloth/Apertus-8B-Instruct-2509-unsloth-bnb-4bit`.

Optional offline mode (forces local-only loads):

```bash
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
```

### 4) Verify the model files

```bash
ls -lh "$FUZZYBOT_MODELS_DIR/Apertus-8B-Instruct-2509" | head
du -sh "$FUZZYBOT_MODELS_DIR/Apertus-8B-Instruct-2509"
```

Quick load test:

```bash
python - <<'PY'
import os
from transformers import AutoTokenizer, AutoModelForCausalLM
base = os.environ.get("FUZZYBOT_MODELS_DIR", os.path.expanduser("~/models"))
p = os.path.join(base, "Apertus-8B-Instruct-2509")
tok = AutoTokenizer.from_pretrained(p, local_files_only=True)
m = AutoModelForCausalLM.from_pretrained(p, local_files_only=True)
print("OK loaded:", type(m).__name__)
PY
```

### 5) Place PDFs for embeddings

```bash
mkdir -p ~/FuzzyBot_HSBI/Embeddings_Creator/data/raw
```

Copy PDFs into that folder and run:

```bash
cd ~/FuzzyBot_HSBI/Embeddings_Creator
python build_pdf_embeddings.py
```

### 6) Start the server

Use tmux + Slurm on the login node:

- See [docs/RUNBOOK_run_llm_server_on_cluster.md](RUNBOOK_run_llm_server_on_cluster.md)

### 7) One-liner: update repo + deps

```bash
cd ~/FuzzyBot_HSBI && \
git pull --rebase && \
source ~/miniconda3/etc/profile.d/conda.sh && \
conda activate fuzzybot && \
pip install -r env/requirements-llm-server.txt
```

## Client VM install

### 1) Create deploy folder

```bash
sudo mkdir -p /opt/Fuzzybot_Server
sudo chown $USER:$USER /opt/Fuzzybot_Server
```

### 2) Copy UI + proxy files

From a local machine (repo checkout):

```bash
scp -r WebClient/client/* <VM_USER>@fuzzybot.yai.hsbi.de:/opt/Fuzzybot_Server/
scp WebClient/server/proxy.py <VM_USER>@fuzzybot.yai.hsbi.de:/opt/Fuzzybot_Server/

If Python on the VM is missing `requests`, install it directly or copy the VM
requirements file from the repo:

```bash
pip install requests==2.32.5
# or, if the repo exists on the VM:
# pip install -r ~/FuzzyBot_HSBI/env/requirements-vm.txt
```
```

If the VM still runs `ProxyRequest.py`, replace it with `proxy.py` for consistency.

Example:

```bash
cd /opt/Fuzzybot_Server
mv ProxyRequest.py proxy.py
pkill -f ProxyRequest.py || true
python proxy.py
```

### 3) Run the proxy (on the VM)

```bash
cd /opt/Fuzzybot_Server
export PROXY_PORT=8000
export APERTUS_URL=http://127.0.0.1:9000
python proxy.py
```

### 4) Keep the SSH tunnel alive (on the VM)

```bash
tmux new -s tunnel
ssh -i ~/.ssh/id_fuzzybot_ed25519 -L 9000:cpnXXX:9000 <USER>@usr.yai.hsbi.de
```

Detach with `Ctrl + b` then `d`.

### 5) Apache reverse proxy

Apache proxies `https://fuzzybot.yai.hsbi.de/` to `http://127.0.0.1:8000/`.
The VM already has a vhost; verify it matches the deployment.

## Where files live

Cluster:
- Repo: `~/FuzzyBot_HSBI`
- Embeddings DB: `~/FuzzyBot_HSBI/LLM_Server/rag/db`
- Models: `/scratch/$USER/fuzzybot_models/<MODEL_NAME>` (recommended)

VM:
- UI + proxy: `/opt/Fuzzybot_Server`
- Apache vhost files: `/etc/httpd/conf.d/vhost_fuzzybot.yai.hsbi.de-80.conf`,
  `/etc/httpd/conf.d/vhost_fuzzybot.yai.hsbi.de-443.conf`
