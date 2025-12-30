# RUNBOOK: FuzzyBot_HSBI Main (Architecture + Ops Overview)

Version: 2025-12-28  
Purpose: Explain where each component runs and how long-running jobs stay alive.

## Key ideas

- The LLM server runs on a GPU node and starts inside a Slurm job.
- GPU nodes are requested via `salloc` (or `sbatch`).
- The login node has internet access; GPU nodes typically do not.
- Long-running jobs are launched from a `tmux` session on the login (CPU) node so
  they survive SSH disconnects.
- The client UI runs on a separate VM and forwards requests to the GPU node.

## Where things run

- Login node (CPU): start `tmux`, submit Slurm jobs, keep long-running sessions alive.
- GPU node (Slurm allocation): run `python LLM_Server/server.py`.
- Client VM: run `WebClient/server/proxy.py` and expose a browser UI.

Start `server.py` directly; no Slurm helper scripts are used.

## Standard flow (end-to-end)

1) SSH to the login node (CPU).
2) Start a `tmux` session.
3) Request a GPU allocation (`salloc`).
4) Enter the GPU node (`srun --pty bash -l`).
5) Start the LLM server inside the allocation.
6) Detach tmux so the job keeps running.
7) From the client VM (or a local machine), open an SSH tunnel to the GPU node.
8) Run the UI proxy on the client VM and open the browser.

## Runbooks

- [Start the server with tmux + Slurm](RUNBOOK_run_llm_server_on_cluster.md)
- [Build PDF embeddings (LanceDB)](RUNBOOK_embeddings_creator.md)
- [VM structure and notes](VM_STRUCTURE.md)
- [tmux + Slurm quick guide](TOOLS_tmux_slurm.md)
