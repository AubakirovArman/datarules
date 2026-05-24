# DataRules

DataRules is a new isolated application in this checkout for document ingestion,
extraction, normalization, schema proposal, and search/RAG access.

The project is intentionally isolated from existing applications:

- local Python dependencies live in `.venv`;
- default database is isolated PostgreSQL on host port `55433`;
- PostgreSQL image is ParadeDB with `vector`, `pg_search`, and `pg_trgm`;
- API uses port `8017`;
- frontend uses port `5177`;
- Gemma/vLLM uses port `8018`;
- Gemma is pinned to GPU `id=2` through `CUDA_VISIBLE_DEVICES=2`.

## Model

The full multimodal model is downloaded here:

```text
/mnt/hf_model_weights/arman/3bit/models/google-gemma-4-31B-it
```

Current checkpoint size is about 58 GiB and includes two safetensors shards.

## Setup

```bash
cd /mnt/hf_model_weights/arman/3bit/sites/datarules
scripts/setup_venv.sh
cd frontend && npm install && cd ..
```

## Run App

Terminal 1:

```bash
scripts/run_api.sh
```

Terminal 2:

```bash
scripts/run_frontend.sh
```

Open:

```text
http://127.0.0.1:5177
```

## Live End-to-End Smoke

After the API, frontend, Postgres, Gemma, and embeddings services are running,
verify the real runtime path:

```bash
PYTHONPATH=backend .venv/bin/python scripts/live_e2e_smoke.py
```

The smoke creates a temporary dataset, uploads two documents, runs ingestion,
confirms routing, checks schema chat context, creates and materializes a new
table, verifies readiness, search, ask, golden evaluation snapshots, and the
golden regression gate, then drops the temporary `e2e_smoke_*` tables and
deletes its own dataset rows.

To inspect the created data instead of cleaning it up automatically:

```bash
DATARULES_SMOKE_KEEP_DATA=1 PYTHONPATH=backend .venv/bin/python scripts/live_e2e_smoke.py
```

## Run Gemma On GPU 2

Install vLLM only when model serving is needed:

```bash
scripts/install_vllm.sh
scripts/serve_gemma_gpu2.sh
```

Then set:

```bash
ENABLE_GEMMA_CALLS=true
GEMMA_BASE_URL=http://127.0.0.1:8018/v1
```

The API can run without live Gemma. In that mode it stores extracted canonical
JSON and creates a deterministic fallback schema proposal with mandatory source
references.

## Optional Infrastructure

These services use separate ports and named volumes:

```bash
docker compose up -d postgres redis minio
```

Postgres URL:

```text
postgresql+psycopg://datarules:datarules@127.0.0.1:55433/datarules
```

## Ingestion Runtime Guardrails

Ingestion jobs store `attempt_count`, `max_attempts`, and `heartbeat_at`.
The API startup recovery requeues unfinished jobs until `INGESTION_MAX_ATTEMPTS`
is reached, then marks them failed. `/diagnostics` includes
`ingestion_runner` with active/stale job counts. Tune stale detection with:

```bash
INGESTION_MAX_ATTEMPTS=3
INGESTION_STALE_SECONDS=900
```

## Production Secrets

External database URLs are encrypted before they are stored in DataRules.
`scripts/run_api.sh` creates a stable local key in `storage/runtime.env` when
`DATARULES_SECRET_KEY` is not set. The file is created with `600` permissions
and is ignored with the rest of `storage/`.

For a managed deployment, generate a key and set `DATARULES_SECRET_KEY` in
`.env` or the process environment:

```bash
scripts/generate_secret_key.sh
```

If neither `.env`, process environment, nor `storage/runtime.env` provides a
key, the API reports `secret_storage=development_fallback` from `/health`. Do
not use that fallback for production data.

## Product Flow

1. Create a dataset.
2. Upload TXT, CSV, XLSX, DOCX, PPTX, or PDF files.
3. Start ingestion.
4. Inspect job progress and events.
5. Review document summaries and routing suggestions.
6. Choose an existing table from the catalog or create a new table.
7. Preview validated rows, then confirm the load.
8. Agent search tables are prepared with source references, `vector`, BM25/keyword, and metadata columns.

Every extracted block is stored with document, page/sheet/slide context,
confidence, and canonical JSON under `storage/canonical`.

## License

DataRules is free for private and non-commercial use.

Commercial use requires a separate paid written license from the copyright
holder. See [LICENSE](LICENSE) for the full terms.
