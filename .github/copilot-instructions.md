# Copilot Instructions — csclbot project

- The user is **Gerry Stahl**; address him as Gerry. Tone is collegial and concise, no filler.
- Do not create summary markdown files unless asked.

## Project

csclbot ("The CSCL Bot") is a public RAG chat interface over Gerry's books/chapters and ijCSCL journal articles, live at https://csclbot.gerrystahl.net on Azure Container Apps (see `documentation/deployment.md`). It was built from the older projects `../elibrary` and `../anniversary`; all future work happens in this repository (`GerryStahl/csclbot`) and the other repositories are not changed unless Gerry asks.

## Conventions

- Python venv: always `.venv/bin/python`.
- Type hints on signatures, module docstrings on scripts, `pathlib.Path`, paths relative to `Path(__file__).resolve().parent.parent`.
- Never hardcode API keys; `ANTHROPIC_API_KEY` comes from the environment.
- Claude model for labelling/summaries: `claude-haiku-4-5-20251001`.

## Constraints

- Gerry holds copyright on his own books/chapters only. For journal articles, the hosted app must hold no full text: store only embeddings, citation metadata and short summaries, and cap any quotation. Article text stays under `data/private/` (git-ignored).
- Article titles come only from `data/inputs/metadata_corrections.csv` and `data/inputs/ijcscl.json` (copies from the Anniversary project); never re-parse them from PDFs.
- Embedding models differ between sources (`e5-base-v2` 768-dim vs `all-MiniLM-L6-v2` 384-dim); one index must use one model.
- Hosted version is Claude-only (no Ollama), with rate limits and a spend cap.
- Secrets: never print, trace or log `ANTHROPIC_API_KEY` or other secrets (no `bash -x` on scripts that handle them); read only filtered output. Never commit secrets, the MaxMind database, usage logs or PDFs.
- Do not create or change Azure resources without Gerry's confirmation; deployment steps are in `documentation/deployment.md`.
