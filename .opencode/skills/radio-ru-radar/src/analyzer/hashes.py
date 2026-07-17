import hashlib
import json
import re
from typing import Optional


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_query(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def compute_query_hash(query_text: str) -> str:
    return _sha256(normalize_query(query_text))


def compute_content_hash(
    excerpt: Optional[str], topic: str = "", author: str = ""
) -> str:
    raw = (author or "") + "\n" + (topic or "") + "\n" + (excerpt or "")
    return _sha256(raw)


def compute_params_hash(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return _sha256(canonical)