from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from nicole.application import NicoleApplication
from nicole.runtime import RuntimeHostBindings


EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "birthday_cli" / "main.nic"


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

    app = NicoleApplication(
        EXAMPLE_PATH,
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
    assert app.checked is None
    checked = app.compile()
    assert app.checked is checked
    assert "@app.run" in checked.export_contract.words
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
