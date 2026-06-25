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


def compute_rubric_hash(criteria: dict) -> str:
    canonical = json.dumps(criteria, sort_keys=True, ensure_ascii=False)
    return _sha256(canonical)


def compute_content_hash(content_md: Optional[str], title: str = "", excerpt: str = "") -> str:
    if content_md:
        return _sha256(content_md)
    return _sha256((title or "") + "\n" + (excerpt or ""))