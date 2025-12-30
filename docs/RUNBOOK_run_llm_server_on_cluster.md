# RUNBOOK: Start Apertus RAG Server on HSBI Cluster (tmux + Slurm + tunnel)

Version: 2025-12-28  
Goal: Keep the model server running even if the SSH window closes or the laptop sleeps.  
Assumption: Repo is at `~/FuzzyBot_HSBI` on the cluster.  
See also: [Main runbook](RUNBOOK_main.md)

## Why tmux + Slurm

- The login node is CPU-only, so the LLM server does not run there.
- GPU nodes are only available inside Slurm allocations.
- The login node has internet access; GPU nodes typically do not.
- Run the server inside a `tmux` session on the login node so the Slurm job
  stays alive even if SSH disconnects.
- Start `server.py` directly; no Slurm helper scripts are used.

## 0) Optional: SSH key setup (new machine only)

Generate a key (local machine):

```bash
ssh-keygen -t ed25519 -a 100 -C "yourai-access"
```

The `-C` comment is only a local label. Use a generic label if you prefer
to avoid personal identifiers.

Add the public key to the cluster (password login once):

```powershell
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
ssh <USER>@usr.yai.hsbi.de
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

Alternative: add the public key via the web UI (VPN required):

1) Open `https://usr.yai.hsbi.de` (self-signed cert warning on first visit).
2) Files App -> Home Directory -> enable "Show dotfiles".
3) Open `.ssh/authorized_keys` -> Edit -> paste the key as a new line -> Save.

## 1) SSH into cluster login node (CPU)

```bash
ssh -i ~/.ssh/id_ed25519 <USER>@usr.yai.hsbi.de
```

Expected prompt:

```text
[<USER>@usr000 ~]$
```

## 2) Start tmux on the login node

If tmux is missing, ask the admins or use `screen` as a fallback.

```bash
tmux new -s fuzzybot
```

Detach later with:

- `Ctrl + b` then `d`

## 3) Request a Slurm GPU allocation (inside tmux)

24 hours example (A100, 64 GB RAM):

```bash
salloc -A <ACCOUNT> --qos=<QOS> -p gpu-computing \
  --nodes=1 --ntasks=1 --cpus-per-task=8 --mem=64G --gres=gpu:a100:1 --time=24:00:00
```

96 hours example (A100, 250 GB RAM):

```bash
salloc -A <ACCOUNT> --qos=<QOS> -p gpu-computing \
  --nodes=1 --ntasks=1 --gres=gpu:a100:1 --mem=250G --time=4-00:00:00
```

If successful, output includes:

```text
salloc: Granted job allocation 7311
salloc: Nodes cpnXXX are ready for job
```

## 4) Enter the GPU node (within the job)

```bash
srun --jobid="$SLURM_JOB_ID" --overlap --pty bash -l
```

Expected prompt:

```text
[<USER>@cpnXXX ~]$
```

## 5) Activate environment

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate fuzzybot
```

## 6) Start the server (inside the GPU allocation)

```bash
cd ~/FuzzyBot_HSBI/LLM_Server
python server.py
```

Expected output includes:

```text
INFO:     Uvicorn running on http://0.0.0.0:9000
```

## 7) Detach from tmux (server keeps running)

- `Ctrl + b` then `d`

## 8) Open an SSH tunnel (from the client VM or a local machine)

Replace `cpnXXX` with the node from `$SLURM_JOB_NODELIST`.

Windows PowerShell:

```powershell
$KEY_PATH = "$env:USERPROFILE\.ssh\id_ed25519"
ssh -i $KEY_PATH -L 9000:cpnXXX:9000 <USER>@usr.yai.hsbi.de
```

macOS / Linux:

```bash
ssh -i ~/.ssh/id_ed25519 -L 9000:cpnXXX:9000 <USER>@usr.yai.hsbi.de
```

The local client now reaches the model at:

- `http://127.0.0.1:9000`

## 9) Test the API

```bash
curl -X POST "http://127.0.0.1:9000/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"apertus\",\"messages\":[{\"role\":\"user\",\"content\":\"Hello cluster\"}]}"
```
