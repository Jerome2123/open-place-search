from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from open_places_manticore import manticore
from open_places_manticore.parsers import iter_source_records
from open_places_manticore.storage import (
    build_search_documents,
    export_search_documents_tsv,
    ingest_records,
    init_db,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="open-places",
        description="Ingest public place data, normalize it in Postgres, and index it in Manticore.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    init_parser = subcommands.add_parser("init-db", help="Create or update Postgres tables")
    init_parser.add_argument("--database-url", required=True)
    init_parser.add_argument("--schema", default=None)

    ingest_parser = subcommands.add_parser("ingest", help="Import a public data extract")
    ingest_parser.add_argument("--database-url", required=True)
    ingest_parser.add_argument("--source", required=True)
    ingest_parser.add_argument("--path", required=True)
    ingest_parser.add_argument("--country-code", default=None)
    ingest_parser.add_argument("--commit-every", type=int, default=1000)

    build_documents_parser = subcommands.add_parser(
        "build-documents", help="Build durable Manticore source documents in Postgres"
    )
    build_documents_parser.add_argument("--database-url", required=True)
    build_documents_parser.add_argument("--commit-every", type=int, default=1000)

    export_parser = subcommands.add_parser("export-tsv", help="Export search documents as TSV")
    export_parser.add_argument("--database-url", required=True)
    export_parser.add_argument("--out", required=True)

    load_parser = subcommands.add_parser("load-manticore", help="Bulk-load TSV into Manticore")
    load_parser.add_argument("--host", required=True)
    load_parser.add_argument("--port", type=int, default=9308)
    load_parser.add_argument("--tsv", required=True)
    load_parser.add_argument("--schema", default=str(Path("sql") / "manticore" / "poi_v1.sql"))
    load_parser.add_argument("--index", default="poi_v1")
    load_parser.add_argument("--batch-size", type=int, default=5000)
    load_parser.add_argument("--timeout-seconds", type=float, default=30.0)
    load_parser.add_argument("--skip-schema", action="store_true")
    return parser


def _connect(database_url: str):
    import psycopg

    return psycopg.connect(database_url)


def _print_result(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
    sys.stdout.write("\n")


def run(argv: Sequence[str] | None = None) -> dict[str, object]:
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    if args.command == "load-manticore":
        loaded = asyncio.run(
            manticore.load_tsv(
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
        return {"command": args.command, "loaded": loaded, "index": args.index}

    with _connect(args.database_url) as conn:
        if args.command == "init-db":
            init_db(conn, schema_path=Path(args.schema) if args.schema else None)
            return {"command": args.command, "status": "ok"}
        if args.command == "ingest":
            records = iter_source_records(
                args.path,
                args.source,
                default_country_code=args.country_code,
            )
            imported = ingest_records(conn, records, commit_every=args.commit_every)
            return {"command": args.command, "imported": imported, "source": args.source}
        if args.command == "build-documents":
            built = build_search_documents(conn, commit_every=args.commit_every)
            return {"command": args.command, "built": built}
        if args.command == "export-tsv":
            if args.out == "-":
                written = export_search_documents_tsv(conn, sys.stdout)
            else:
                out_path = Path(args.out)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with out_path.open("w", encoding="utf-8", newline="") as handle:
                    written = export_search_documents_tsv(conn, handle)
            return {"command": args.command, "written": written, "out": args.out}

    raise ValueError(f"Unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> None:
    _print_result(run(argv))


if __name__ == "__main__":
    main()
