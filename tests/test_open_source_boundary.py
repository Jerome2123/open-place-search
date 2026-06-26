from pathlib import Path


def test_repository_does_not_include_disallowed_provider_or_product_terms() -> None:
    root = Path(__file__).resolve().parents[1]
    banned = [
        "at" + "lyss",
        "lite" + "api",
        "mich" + "elin",
        "via" + "tor",
        "goo" + "gle places",
        "goo" + "gle_places",
    ]
    allowed_dirs = {".git", ".pytest_cache", "__pycache__", ".ruff_cache"}

    matches: list[str] = []
    for path in root.rglob("*"):
        if any(part in allowed_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        if path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for term in banned:
            if term in text:
                matches.append(str(path.relative_to(root)))

    assert matches == []

