from open_place_search.cli import build_parser


def test_cli_exposes_library_workflow_commands() -> None:
    parser = build_parser()

    assert parser.parse_args(["init-db", "--database-url", "postgresql://local/db"]).command == "init-db"
    assert (
        parser.parse_args(
            [
                "ingest",
                "--database-url",
                "postgresql://local/db",
                "--source",
                "geonames",
                "--path",
                "cities.txt",
            ]
        ).command
        == "ingest"
    )
    assert parser.parse_args(["build-documents", "--database-url", "postgresql://local/db"]).command == "build-documents"
    assert parser.parse_args(["export-tsv", "--database-url", "postgresql://local/db", "--out", "-"]).command == "export-tsv"
    assert parser.parse_args(["load-manticore", "--host", "127.0.0.1", "--tsv", "places.tsv"]).command == "load-manticore"

