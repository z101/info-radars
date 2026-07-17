def normalize_scores(results: list[dict], key: str = "score") -> list[dict]:
    if not results:
        return results

    scores = [r.get(key, 0) or 0 for r in results]
    min_s = min(scores)
    max_s = max(scores)

    if max_s == min_s:
        for r in results:
            r[f"{key}_normalized"] = 100
        return results

    for r in results:
        raw = r.get(key, 0) or 0
        r[f"{key}_normalized"] = round((raw - min_s) / (max_s - min_s) * 100, 1)

    return results