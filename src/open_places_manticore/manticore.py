from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

import httpx

MANTICORE_COLUMNS = [
    "id",
    "name",
    "trusted_aliases",
    "code_aliases",
    "weak_aliases",
    "category_text",
    "category_ids",
    "scope_ids",
    "country_scope_id",
    "admin1_scope_id",
    "city_scope_id",
    "best_scope_id",
    "primary_scope_id",
    "scope_display_hash",
    "lat",
    "lng",
    "h3_r5",
    "h3_r6",
    "h3_r7",
    "place_type",
    "subtype",
    "provider",
    "country_code",
    "quality_tier",
    "global_search_tier",
    "rank_score",
    "popularity_score",
    "global_name_score",
    "global_popularity_score",
    "global_category_score",
    "category_quality_score",
    "source_quality_score",
    "review_count",
    "saved_count",
    "is_global_autocomplete",
    "is_global_exact_searchable",
    "is_global_prefix_searchable",
    "has_photo",
    "has_description",
    "flags",
]

MULTI_COLUMNS = {"category_ids", "scope_ids"}
BOOL_COLUMNS = {
    "is_global_autocomplete",
    "is_global_exact_searchable",
    "is_global_prefix_searchable",
    "has_photo",
    "has_description",
}
INT_COLUMNS = {
    "country_scope_id",
    "admin1_scope_id",
    "city_scope_id",
    "best_scope_id",
    "primary_scope_id",
    "scope_display_hash",
    "h3_r5",
    "h3_r6",
    "h3_r7",
    "quality_tier",
    "global_search_tier",
    "review_count",
    "saved_count",
    "flags",
}
FLOAT_COLUMNS = {
    "lat",
    "lng",
    "rank_score",
    "popularity_score",
    "global_name_score",
    "global_popularity_score",
    "global_category_score",
    "category_quality_score",
    "source_quality_score",
}


def split_sql_statements(schema: str) -> list[str]:
    lines: list[str] = []
    for line in schema.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        lines.append(line.rstrip())
    return [statement.strip() for statement in "\n".join(lines).split(";") if statement.strip()]


def _clean(value: object) -> str:
    text = str(value if value is not None else "")
    return text.replace("\t", " ").replace("\r", " ").replace("\n", " ")


def _csv_ints(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return ",".join(str(int(item)) for item in value if item is not None)
    return str(value)


def _bool_int(value: object) -> int:
    return 1 if bool(value) else 0


def render_document_for_tsv(document: Mapping[str, object]) -> dict[str, object]:
    row = {column: document.get(column, "") for column in MANTICORE_COLUMNS}
    row["id"] = document.get("id") or document.get("doc_id") or ""
    row["category_ids"] = _csv_ints(document.get("category_ids"))
    row["scope_ids"] = _csv_ints(document.get("scope_ids"))
    for column in BOOL_COLUMNS:
        row[column] = _bool_int(document.get(column))
    return row


def serialize_tsv_row(row: Mapping[str, object], columns: list[str] | None = None) -> str:
    selected_columns = columns or MANTICORE_COLUMNS
    rendered = render_document_for_tsv(row)
    return "\t".join(_clean(rendered.get(column)) for column in selected_columns)


def _int_list(value: str) -> list[int]:
    if not value:
        return []
    return [int(item) for item in value.split(",") if item]


def _int(value: str) -> int:
    return int(value) if value else 0


def _float(value: str) -> float:
    return float(value) if value else 0.0


def _bool(value: str) -> bool:
    return value.lower() in {"1", "true", "yes"}


def document_from_tsv_values(values: Sequence[str]) -> tuple[int, dict[str, Any]]:
    if len(values) != len(MANTICORE_COLUMNS):
        raise ValueError(f"expected {len(MANTICORE_COLUMNS)} TSV columns, got {len(values)}")
    row = dict(zip(MANTICORE_COLUMNS, values, strict=True))
    doc_id = int(row["id"])
    document: dict[str, Any] = {}
    for column, value in row.items():
        if column == "id":
            continue
        if column in MULTI_COLUMNS:
            document[column] = _int_list(value)
        elif column in BOOL_COLUMNS:
            document[column] = _bool(value)
        elif column in INT_COLUMNS:
            document[column] = _int(value)
        elif column in FLOAT_COLUMNS:
            document[column] = _float(value)
        else:
            document[column] = value
    return doc_id, document


def build_bulk_payload(documents: Sequence[tuple[int, Mapping[str, Any]]], *, index: str) -> str:
    return (
        "\n".join(
            json.dumps(
                {"replace": {"index": index, "id": doc_id, "doc": dict(document)}},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            for doc_id, document in documents
        )
        + "\n"
    )


@contextmanager
def open_tsv(path: Path | str) -> Iterator[TextIO]:
    if str(path) == "-":
        yield sys.stdin
        return
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        yield handle


async def execute_sql(client: httpx.AsyncClient, *, host: str, port: int, statement: str) -> None:
    response = await client.post(
        f"http://{host}:{int(port)}/sql?mode=raw",
        content=statement.encode("utf-8"),
        headers={"Content-Type": "text/plain"},
    )
    response.raise_for_status()


async def post_bulk(client: httpx.AsyncClient, *, host: str, port: int, payload: str) -> None:
    response = await client.post(
        f"http://{host}:{int(port)}/bulk",
        content=payload.encode("utf-8"),
        headers={"Content-Type": "application/x-ndjson"},
    )
    response.raise_for_status()


async def load_tsv(
    *,
    host: str,
    port: int,
    tsv_path: Path,
    schema_path: Path | None = None,
    index: str = "poi_v1",
    batch_size: int = 5000,
    timeout_seconds: float = 30.0,
    skip_schema: bool = False,
) -> int:
    loaded = 0
    timeout = httpx.Timeout(timeout_seconds)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if schema_path is not None and not skip_schema:
            schema = schema_path.read_text(encoding="utf-8")
            for statement in split_sql_statements(schema):
                await execute_sql(client, host=host, port=port, statement=statement)
        batch: list[tuple[int, dict[str, Any]]] = []
        with open_tsv(tsv_path) as handle:
            reader = csv.reader(handle, delimiter="\t")
            for values in reader:
                if not values:
                    continue
                batch.append(document_from_tsv_values(values))
                if len(batch) >= batch_size:
                    await post_bulk(
                        client,
                        host=host,
                        port=port,
                        payload=build_bulk_payload(batch, index=index),
                    )
                    loaded += len(batch)
                    batch = []
        if batch:
            await post_bulk(
                client,
                host=host,
                port=port,
                payload=build_bulk_payload(batch, index=index),
            )
            loaded += len(batch)
    return loaded


def build_load_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load Manticore TSV documents")
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=9308)
    parser.add_argument("--tsv", required=True)
    parser.add_argument("--schema")
    parser.add_argument("--index", default="poi_v1")
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--skip-schema", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_load_parser().parse_args(list(argv) if argv is not None else None)
    loaded = asyncio.run(
        load_tsv(
            host=args.host,
            port=args.port,
            tsv_path=Path(args.tsv),
            schema_path=Path(args.schema) if args.schema else None,
            index=args.index,
            batch_size=args.batch_size,
            timeout_seconds=args.timeout_seconds,
            skip_schema=args.skip_schema,
        )
    )
    sys.stdout.write(json.dumps({"loaded": loaded, "index": args.index}, indent=2))
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
