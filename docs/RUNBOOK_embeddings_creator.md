# RUNBOOK: Build PDF Embeddings (LanceDB) for RAG

Version: 2025-12-28  
Purpose: Build/update the LanceDB table used by the RAG server.  
Repo path on cluster: `~/FuzzyBot_HSBI`  
Script: `~/FuzzyBot_HSBI/Embeddings_Creator/build_pdf_embeddings.py`  
See also: [Main runbook](RUNBOOK_main.md)

## Notes

- Embeddings can run on a CPU node (GPU optional).
- The output DB must be on a path visible to the GPU node (shared home or scratch).
- Optional source: Convert [docs/CLUSTER_GUIDE_GENERAL_DE.md](CLUSTER_GUIDE_GENERAL_DE.md) to PDF and place it in the raw PDF folder.

## Defaults

- PDF input: `~/FuzzyBot_HSBI/Embeddings_Creator/data/raw`
- DB output: `~/FuzzyBot_HSBI/LLM_Server/rag/db`
- Table: `pdf_chunks`
- Model: `sentence-transformers/all-MiniLM-L6-v2`

## Environment overrides

Paths:
- `FUZZYBOT_DB_DIR` -> base DB directory (preferred)
- `EMBEDDING_DB_URI` -> DB directory (overrides `FUZZYBOT_DB_DIR`)
- `FUZZYBOT_PDF_DIR` -> PDF input directory (preferred)
- `EMBEDDING_PDF_DIR` -> PDF input directory (override)

Table + model:
- `EMBEDDING_TABLE_NAME` (default: `pdf_chunks`)
- `EMBEDDING_MODEL_PATH` (default: `sentence-transformers/all-MiniLM-L6-v2`)

Chunking:
- `EMBEDDING_CHUNK_SIZE` (default: `800`)
- `EMBEDDING_CHUNK_OVERLAP` (default: `200`)
- `EMBEDDING_MIN_CHARS` (default: `100`)
- `EMBEDDING_BATCH_SIZE` (default: `64`)

Rebuild:
- `CLEAR_TABLE=1` -> drop and recreate the table

## 1) SSH + tmux

```bash
ssh -i ~/.ssh/id_ed25519 <USER>@usr.yai.hsbi.de
tmux new -s embed
```

## 2) Allocate a compute session (CPU is usually enough)

```bash
salloc -A <ACCOUNT> -p <PARTITION> \
  --nodes=1 --ntasks=1 --cpus-per-task=8 --mem=32G --time=04:00:00
```

Enter the allocated node:

```bash
srun --jobid="$SLURM_JOB_ID" --overlap --pty bash -l
```

## 3) Activate conda environment

```bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate fuzzybot
```

## 4) Set paths (recommended)

```bash
export FUZZYBOT_DB_DIR=~/FuzzyBot_HSBI/LLM_Server/rag/db
export EMBEDDING_DB_URI="$FUZZYBOT_DB_DIR"
export EMBEDDING_TABLE_NAME="pdf_chunks"
export EMBEDDING_MODEL_PATH="sentence-transformers/all-MiniLM-L6-v2"
```

Optional PDF folder override:

```bash
export FUZZYBOT_PDF_DIR=~/FuzzyBot_HSBI/Embeddings_Creator/data/raw
# or:
# export EMBEDDING_PDF_DIR=/some/other/path
```

## 5) Prepare input PDFs

```bash
mkdir -p ~/FuzzyBot_HSBI/Embeddings_Creator/data/raw
```

Copy PDFs into that folder:

```bash
scp -r /path/to/pdfs/*.pdf <USER>@usr.yai.hsbi.de:~/FuzzyBot_HSBI/Embeddings_Creator/data/raw/
```

## 6) Run the embeddings builder

```bash
cd ~/FuzzyBot_HSBI/Embeddings_Creator
python build_pdf_embeddings.py
```

## 7) Verify output

```bash
ls -lah "$EMBEDDING_DB_URI"
```

```bash
python -c "import lancedb; db=lancedb.connect('$EMBEDDING_DB_URI'); print(db.table_names())"
```

Optional row count:

```bash
python -c "import lancedb; db=lancedb.connect('$EMBEDDING_DB_URI'); t=db.open_table('pdf_chunks'); print(t.count_rows())"
```

## 8) Rebuild from scratch (optional)

```bash
export CLEAR_TABLE=1
cd ~/FuzzyBot_HSBI/Embeddings_Creator
python build_pdf_embeddings.py
```

## 9) Cleanup

Detach tmux:

- `Ctrl + b` then `d`

End the job:

```bash
exit   # leave compute node
exit   # release salloc
```
