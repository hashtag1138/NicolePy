from pathlib import Path
import sys
import re
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nicole.application import NicoleApplication
from nicole.host_abi import HostEffect, HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.runtime import RuntimeHostBindings


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "birthday_cli" / "main.nic"


def _signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def _rewrite_direct_host_calls_to_import_aliases(source: str, host_word_names: list[str]) -> str:
    rewritten = source
    used_aliases: list[tuple[str, str]] = []
    for host_name in sorted(host_word_names, key=len, reverse=True):
        if not host_name.startswith("host."):
            continue
        host_suffix = host_name[len("host.") :]
        alias_name = f"h.{host_suffix}"
        pattern = re.compile(rf"(?<![A-Za-z0-9_@.-]){re.escape(host_name)}(?![A-Za-z0-9_.-])")
        rewritten, count = pattern.subn(alias_name, rewritten)
        if count > 0:
            used_aliases.append((host_name, alias_name))

    if not used_aliases:
        return rewritten

    import_lines = [f"  import @{host_name} as {alias_name}\n" for host_name, alias_name in used_aliases]
    output: list[str] = []
    for line in rewritten.splitlines(keepends=True):
        output.append(line)
        stripped = line.strip()
        if stripped.startswith("module @") and stripped != "module @host":
            output.extend(import_lines)
    return "".join(output)


def _birthday_host_contract():
    read_signature = _signature_from_source(
        "module @sig\n  : hostsig { -- text:String } ;\nend-module\n"
    )
    parse_int_signature = _signature_from_source(
        "module @sig\n  : hostsig { text:String -- value:Int } ;\nend-module\n"
    )
    now_int_signature = _signature_from_source(
        "module @sig\n  : hostsig { -- value:Int } ;\nend-module\n"
    )
    out_text_signature = _signature_from_source(
        "module @sig\n  : hostsig { text:String -- } ;\nend-module\n"
    )
    out_int_signature = _signature_from_source(
        "module @sig\n  : hostsig { value:Int -- } ;\nend-module\n"
    )
    return host_contract_from_words(
        [
            HostWord(name="host.console.read", signature=read_signature, effect=HostEffect.DIRTY),
            HostWord(name="host.parse.int", signature=parse_int_signature, effect=HostEffect.PURE),
            HostWord(name="host.now.year", signature=now_int_signature, effect=HostEffect.PURE),
            HostWord(name="host.now.month", signature=now_int_signature, effect=HostEffect.PURE),
            HostWord(name="host.now.day", signature=now_int_signature, effect=HostEffect.PURE),
            HostWord(name="host.out.text", signature=out_text_signature, effect=HostEffect.DIRTY),
            HostWord(name="host.out.int", signature=out_int_signature, effect=HostEffect.DIRTY),
        ]
    )


PROMPTS = [
    "Quel est votre prénom ? ",
    "Quelle est votre année de naissance ? ",
    "Quel est votre mois de naissance ? ",
    "Quel est votre jour de naissance ? ",
]


def _run_birthday_cli(*, inputs: list[str], today: tuple[int, int, int]) -> tuple[str, dict[str, int], list[str]]:
    queue = list(inputs)
    output_segments: list[str] = []
    call_counts = {
        "read": 0,
        "parse_int": 0,
        "now_year": 0,
        "now_month": 0,
        "now_day": 0,
        "out_text": 0,
        "out_int": 0,
    }
    current_year, current_month, current_day = today

    def read_next() -> str:
        call_counts["read"] += 1
        if not queue:
            raise AssertionError("input queue exhausted")
        return queue.pop(0)

    def parse_int(text: str) -> int:
        call_counts["parse_int"] += 1
        return int(text)

    def now_year() -> int:
        call_counts["now_year"] += 1
        return current_year

    def now_month() -> int:
        call_counts["now_month"] += 1
        return current_month

    def now_day() -> int:
        call_counts["now_day"] += 1
        return current_day

    def out_text(text: str) -> None:
        call_counts["out_text"] += 1
        output_segments.append(text)

    def out_int(value: int) -> None:
        call_counts["out_int"] += 1
        output_segments.append(str(value))

    host_contract = _birthday_host_contract()
    source_text = EXAMPLE_PATH.read_text(encoding="utf-8")
    rewritten_source = _rewrite_direct_host_calls_to_import_aliases(
        source_text,
        list(host_contract.words),
    )
    with TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir) / "birthday_cli_imported.nic"
        tmp_path.write_text(rewritten_source, encoding="utf-8")
        app = NicoleApplication(
            tmp_path,
            host_contract=host_contract,
            host_bindings=RuntimeHostBindings(
                {
                    "host.console.read": read_next,
                    "host.parse.int": parse_int,
                    "host.now.year": now_year,
                    "host.now.month": now_month,
                    "host.now.day": now_day,
                    "host.out.text": out_text,
                    "host.out.int": out_int,
                }
            ),
        )

        result = app.run("@app.run")

    assert result is None
    assert queue == []
    assert call_counts["read"] == 4
    assert call_counts["parse_int"] == 3
    assert call_counts["now_year"] == 1
    assert call_counts["now_month"] == 1
    assert call_counts["now_day"] == 1
    assert call_counts["out_text"] > 0
    assert call_counts["out_int"] > 0

    return "".join(output_segments), call_counts, output_segments


def test_birthday_cli_birthday_today() -> None:
    rendered, call_counts, segments = _run_birthday_cli(
        inputs=["Alice", "1990", "5", "25"],
        today=(2026, 5, 25),
    )

    assert segments[:4] == PROMPTS
    assert rendered == "".join(PROMPTS) + "Joyeux 36e anniversaire Alice !"
    assert call_counts["out_int"] == 1


def test_birthday_cli_not_yet_reached_this_year() -> None:
    rendered, call_counts, segments = _run_birthday_cli(
        inputs=["Alice", "1990", "5", "25"],
        today=(2026, 5, 24),
    )

    assert segments[:4] == PROMPTS
    assert rendered == "".join(PROMPTS) + "Bonjour Alice, l'année prochaine vous aurez 36 ans."
    assert call_counts["out_int"] == 1


def test_birthday_cli_already_passed_this_year() -> None:
    rendered, call_counts, segments = _run_birthday_cli(
        inputs=["Alice", "1990", "5", "20"],
        today=(2026, 5, 21),
    )

    assert segments[:4] == PROMPTS
    assert rendered == "".join(PROMPTS) + "Bonjour Alice, l'année prochaine vous aurez 37 ans."
    assert call_counts["out_int"] == 1
