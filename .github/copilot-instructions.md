# Copilot Instructions — csclbot project

- The user is **Gerry Stahl**; address him as Gerry. Tone is collegial and concise, no filler.
- Do not create summary markdown files unless asked.

## Project

csclbot is a public, Azure-hosted RAG chat interface over Gerry's books/chapters (`../elibrary`) and ijCSCL journal articles (`../anniversary`). Both source projects are **read-only archives**; never modify them.

## Conventions

- Python venv: always `.venv/bin/python`.
- Type hints on signatures, module docstrings on scripts, `pathlib.Path`, paths relative to `Path(__file__).resolve().parent.parent`.
- Never hardcode API keys; `ANTHROPIC_API_KEY` comes from the environment.
- Claude model for labelling/summaries: `claude-haiku-4-5-20251001`.

## Constraints

- Gerry holds copyright on his own books/chapters only. For journal articles, the hosted app must hold no full text: store only embeddings, citation metadata and short summaries, and cap any quotation. Article text stays under `data/private/` (git-ignored).
- Article titles come only from `../anniversary/data/metadata_corrections.csv` and its `ijcscl.json`; never re-parse them from PDFs.
- Embedding models differ between sources (`e5-base-v2` 768-dim vs `all-MiniLM-L6-v2` 384-dim); one index must use one model.
- Hosted version is Claude-only (no Ollama), with rate limits and a spend cap.
