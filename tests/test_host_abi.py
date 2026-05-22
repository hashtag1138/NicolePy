from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.host_abi import HostABIError
from nicole.parser import ParseError
from nicole.pipeline import analyze_program
from nicole.symbols import SymbolError


def test_module_local_export_publishes_canonical_name() -> None:
    checked = analyze_program(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    42\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert "@app.run" in checked.export_contract.words
    export_word = checked.export_contract.words["@app.run"]
    assert export_word.export_name == "@app.run"
    assert export_word.internal_name == "@app.run"


def test_export_contract_preserves_leading_at_sign() -> None:
    checked = analyze_program(
        "module @app\n"
        "  : run { -- n:Int }\n"
        "    1\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
    )

    assert "@app.run" in checked.export_contract.words
    assert "app.run" not in checked.export_contract.words


def test_import_alias_does_not_change_canonical_export_name() -> None:
    checked = analyze_program(
        "module @core\n"
        "  : run { -- n:Int }\n"
        "    7\n"
        "  ;\n"
        "  export : run\n"
        "end-module\n"
        "import @core as c\n"
        "module @app\n"
        "  : use { -- n:Int }\n"
        "    c.run\n"
        "  ;\n"
        "end-module\n"
    )

    assert set(checked.export_contract.words.keys()) == {"@core.run"}


def test_duplicate_canonical_export_is_rejected() -> None:
    with pytest.raises(SymbolError, match="duplicate export declaration"):
        analyze_program(
            "module @app\n"
            "  : run { -- n:Int }\n"
            "    1\n"
            "  ;\n"
            "  export : run\n"
            "  export : run\n"
            "end-module\n"
        )


def test_export_target_must_exist() -> None:
    with pytest.raises(SymbolError, match="export target does not exist"):
        analyze_program(
            "module @app\n"
            "  export : missing\n"
            "end-module\n"
        )


def test_export_target_must_be_same_module_module_level_word() -> None:
    with pytest.raises(SymbolError, match="export target does not exist"):
        analyze_program(
            "module @lib\n"
            "  : run { -- n:Int }\n"
            "    1\n"
            "  ;\n"
            "end-module\n"
            "import @lib.run as run\n"
            "module @app\n"
            "  export : run\n"
            "end-module\n"
        )


def test_export_target_cannot_be_subword() -> None:
    with pytest.raises(SymbolError, match="module-level"):
        analyze_program(
            "module @app\n"
            "  : parent { -- }\n"
            "    : child { -- }\n"
            "    ;\n"
            "  ;\n"
            "  export : child\n"
            "end-module\n"
        )


def test_legacy_flat_export_syntax_is_not_public_behavior() -> None:
    with pytest.raises(ParseError, match="export declaration is only allowed inside module"):
        analyze_program(
            "export : app.run { -- n:Int }\n"
            "  42\n"
            ";"
        )


def test_exported_word_still_uses_abi_type_validation() -> None:
    with pytest.raises(HostABIError, match="Quote is forbidden across ABI in v1"):
        analyze_program(
            "module @app\n"
            "  : run { -- q:Quote<{ | -- }> }\n"
            "    :[ | -- | ;]\n"
            "  ;\n"
            "  export : run\n"
            "end-module\n"
        )

