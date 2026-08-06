# arXiv Co-work: Paper retrieval agent

## Installing packages:

```powershell
pip install -e .
```

## Database migration:

migration guide is available at /alembic/migrations.md

## Run the app locally

### 1. Running the FastAPI backend:

Terminal 1, running the backend server

```powershell
uvicorn --app-dir src server.main:app --reload --host 0.0.0.0 --port 8000
```

api docs will be available at: http://localhost:8000/docs

### 2. Running celery workers:

Terminal 2, running the pdf download worker

```powershell
$env:PYTHONPATH="src"
celery -A worker.celery_app:celery_app worker -Q paper.pdf_download --pool=solo --loglevel=info
```

Terminal 3, running the parser worker

```powershell
$env:PYTHONPATH="src"
celery -A worker.celery_app:celery_app worker -Q paper.parsing --pool=solo --loglevel=info
```

Terminal 4, running the chunker worker

```powershell
$env:PYTHONPATH="src"
celery -A worker.celery_app:celery_app worker -Q paper.chunking --pool=solo --loglevel=info
```

Terminal 5, running the embedding+indexing worker

```powershell
$env:PYTHONPATH="src"
celery -A worker.celery_app:celery_app worker -Q paper.indexing --pool=solo --loglevel=info
```

## Model plan:

- LLM: Qwen3-8B 4-bit (might upgrade later)
- Embedding: Qwen3-Embedding-0.6B FP16
- Reranker: Qwen3-Reranker-0.6B FP16