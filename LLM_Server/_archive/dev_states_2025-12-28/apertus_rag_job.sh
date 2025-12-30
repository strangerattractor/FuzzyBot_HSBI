#!/usr/bin/env bash
#SBATCH -A slrm-acc_gpu-level-g3x
#SBATCH --qos=qos_slrm-acc_gpu-level-g3x
#SBATCH -p gpu-computing
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --gres=gpu:a100:1
#SBATCH --time=4:00:00
#SBATCH -J apertus_rag
#SBATCH -o %x_%j.out
#SBATCH -e %x_%j.err

echo "[JOB] ================================================"
echo "[JOB] Apertus RAG job started"
echo "[JOB] Job ID      : $SLURM_JOB_ID"
echo "[JOB] Node list   : $SLURM_NODELIST"
echo "[JOB] Start time  : $(date)"
echo "[JOB] ================================================"
echo

# --- Activate conda environment --------------------------------
echo "[JOB] Loading conda environment 'apertus-env'..."
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate apertus-env

echo "[JOB] Python: $(which python)"
python --version || echo "[JOB] WARNING: python --version failed"

# --- Start the server ------------------------------------------
cd "$HOME/bin"
echo "[JOB] Working directory: $(pwd)"
echo "[JOB] Starting serve_apertus_rag_split.py ..."
echo

python serve_apertus_rag_split.py

echo
echo "[JOB] Server stopped. Job exiting at: $(date)"
