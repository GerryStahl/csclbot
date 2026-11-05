"""Shared constants for the csclbot index and search."""
from pathlib import Path

INDEX_DIR = Path(__file__).resolve().parent.parent / "data" / "index"
MODEL_NAME = "intfloat/e5-base-v2"
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
