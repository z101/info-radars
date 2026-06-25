import pytest

from main import create_parser


@pytest.fixture
def parser():
    return create_parser()


class TestCLIFlags:
    @pytest.mark.parametrize("args,attr,expected", [
        (["--category", "led-hacks"], "category", "led-hacks"),
        (["--dry-run", "--category", "led-hacks"], "dry_run", True),
        (["--category", "led-hacks"], "dry_run", False),
        (["--category", "led-hacks", "--full-text"], "full_text", True),
        (["--category", "led-hacks", "--full-text-only"], "full_text_only", True),
        (["--category", "led-hacks", "--metadata-only"], "metadata_only", True),
        (["--category", "led-hacks", "--reset"], "reset", True),
        (["--category", "led-hacks", "--skip-comments"], "skip_comments", True),
        (["--info"], "info", True),
        (["--list-categories"], "list_categories", True),
        (["--export-json", "--category", "led-hacks"], "export_json", True),
        (["--verbose", "--category", "led-hacks"], "verbose", True),
        (["--category", "led-hacks", "--since", "2025-01-01"], "since", "2025-01-01"),
        (["--workers", "5", "--category", "led-hacks"], "workers", 5),
        (["--delay", "0.1", "0.5", "--category", "led-hacks"], "delay", [0.1, 0.5]),
        (["--timeout", "60", "--category", "led-hacks"], "timeout", 60),
        (["--output", "/tmp/out"], "output", "/tmp/out"),
        (["--db", "custom.db", "--category", "led-hacks"], "db", "custom.db"),
        (["--max-pages", "3", "--category", "led-hacks"], "max_pages", 3),
    ])
    def test_flag_values(self, parser, args, attr, expected):
        parsed = parser.parse_args(args)
        assert getattr(parsed, attr) == expected

    def test_max_pages_default(self, parser):
        args = parser.parse_args(["--category", "led-hacks"])
        assert args.max_pages is None