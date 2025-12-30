# Helper: tmux + Slurm quick guide (yourAI cluster)

Version: 2025-12-30  
Purpose: Quick reference for keeping long jobs alive and managing allocations.

## Placeholders used

- `<USER>`: your cluster username
- `<ACCOUNT>`: Slurm account / project allocation
- `<QOS>`: Slurm QOS
- `cpnXXX`: GPU node name

## Why this matters for FuzzyBot_HSBI

- The login node is for setup and job control, not for GPU compute.
- GPU work must run inside a Slurm allocation.
- Use tmux on the login node so the Slurm job survives SSH disconnects.

## tmux essentials

Start a session:

```bash
tmux new -s fuzzybot
```

Detach (keep running):

- `Ctrl+b` then `d`

List sessions:

```bash
tmux ls
```

Reattach:

```bash
tmux attach -t fuzzybot
```

Kill a session:

```bash
tmux kill-session -t fuzzybot
```

## Slurm essentials

Check cluster state and queues:

```bash
sinfo
squeue -u $USER
```

Cancel a job:

```bash
scancel <JOBID>
```

Interactive GPU allocation (then enter the node):

```bash
salloc -A <ACCOUNT> --qos=<QOS> -p gpu-computing \
  --nodes=1 --ntasks=1 --cpus-per-task=8 --mem=64G --gres=gpu:a100:1 --time=24:00:00
srun --jobid="$SLURM_JOB_ID" --overlap --pty bash -l
```

Batch job (submit a script):

```bash
sbatch job_gpu.sh
```

Inspect a job:

```bash
scontrol show job <JOBID>
```

## UI-first tip (yourAI portal)

If you are unsure about Slurm parameters, start a job in the web UI first:

- Use Jupyter or Job Composer to launch a job with the resources you want.
- Then check the job details in "Active Jobs" (node name, job id, wall time).
- Copy the settings into your CLI `salloc` or `sbatch` workflow.

This is often faster than trial-and-error in the terminal.

## Web UI shortcuts that help this project

Portal (VPN required): `https://usr.yai.hsbi.de`

- Shell App: a browser SSH shell on the login node.
- Files App: upload files, edit `~/.ssh/authorized_keys`, manage data.
- Job Composer: edit and submit Slurm batch jobs using templates.
- Active Jobs: view running jobs, node names, and time remaining.
- Jupyter App: launch interactive sessions via Slurm ("My Interactive Sessions").

## Jupyter environment tip

If you need a custom Python env inside Jupyter:

```bash
module load miniconda3
conda create -n <env> python=3.11 conda pip ipykernel
conda activate <env>
python -m ipykernel install --user --name <env> --display-name "<env>"
```

In the Jupyter submit form, set Environment Setup to:

```bash
module load miniconda3
conda activate <env>
```

## Data and quota notes

- Only the login node has internet access for installs and downloads.
- The Files App supports single-file uploads; use `scp` or `rsync` for folders.
- Quota helpers are available on the cluster:

```bash
quota_ceph.max $HOME
quota_ceph.used $HOME
quota_ceph.free $HOME
quota_ceph.overview $HOME
```

- Ceph snapshots are stored under a hidden `/.snap/` directory for recovery.
