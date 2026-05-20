from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nicole.ast_nodes import IdentifierNode, IfNode, PatternKind, QuoteNode
from nicole.host_abi import BindingAvailability, HostEffect, HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.resolver import ResolutionError, resolve
from nicole.signature_collector import collect_signatures
from nicole.symbols import SymbolError
from nicole.standard_symbols import with_standard_symbols


def resolve_source(source: str, *, with_builtins: bool = False):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    if with_builtins:
        symbols = with_standard_symbols(symbols)
    return resolve(program, symbols)


def signature_from_source(source: str):
    return Parser(lex(source)).parse().words[0].signature


def resolve_source_with_host_contract(source: str, host_words):
    program = Parser(lex(source)).parse()
    symbols = collect_signatures(program)
    contract = host_contract_from_words(host_words)
    return resolve(program, symbols, host_contract=contract)


def test_resolve_top_level_word():
    program = resolve_source(
        ": helper { -- } ;\n"
        ": main { -- } helper ;"
    )

    call = program.words[1].body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.name == "helper"
    assert call.resolution.qualified_name == "helper"
    assert call.resolution.declared_dirty is False


def test_resolve_mutual_recursion():
    program = resolve_source(
        ": a { -- } b ;\n"
        ": b { -- } a ;"
    )

    call_a = program.words[0].body.items[0]
    call_b = program.words[1].body.items[0]

    assert call_a.resolution.resolved_symbol is not None
    assert call_a.resolution.resolved_symbol.name == "b"
    assert call_b.resolution.resolved_symbol is not None
    assert call_b.resolution.resolved_symbol.name == "a"


def test_resolve_preserves_declared_dirty_for_user_call():
    program = resolve_source(
        "dirty : helper { -- } ;\n"
        ": main { -- } helper ;"
    )

    call = program.words[1].body.items[0]
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.name == "helper"
    assert call.resolution.declared_dirty is True


def test_resolve_rejects_duplicate_visible_names_before_resolution():
    with pytest.raises(SymbolError, match="duplicate visible name"):
        resolve_source(
            ": id { x:Int -- y:Int } ;\n"
            ": id { x:String -- y:String } ;\n"
            ": main { x:Int -- y:Int } x id ;"
        )


def test_resolve_rejects_top_level_and_subword_homonym():
    with pytest.raises(SymbolError, match="duplicate visible name"):
        resolve_source(
            ": print { -- } ;\n"
            ": outer { -- }\n"
            "  : print { -- } ;\n"
            ";"
        )


def test_resolve_rejects_subword_and_top_level_homonym():
    with pytest.raises(SymbolError, match="duplicate visible name"):
        resolve_source(
            ": outer { -- }\n"
            "  : helper { -- } ;\n"
            ";\n"
            ": helper { -- } ;"
        )


def test_resolve_nested_subword_visible_in_parent():
    program = resolve_source(
        ": invoice { -- }\n"
        "  dirty : subtotal { -- } ;\n"
        "  subtotal\n"
        ";"
    )

    call = program.words[0].body.items[0]
    assert call.resolution.resolved_symbol is not None
    assert call.resolution.resolved_symbol.name == "subtotal"
    assert call.resolution.qualified_name == "invoice.subtotal"
    assert call.resolution.declared_dirty is True


def test_resolve_nested_subword_invisible_outside_parent():
    with pytest.raises(ResolutionError):
        resolve_source(
            ": invoice { -- }\n"
            "  : subtotal { -- } ;\n"
            ";\n"
            ": main { -- }\n"
            "  subtotal\n"
            ";"
        )


def test_resolve_local_parameter_not_rejected():
    program = resolve_source(
        ": square { x:Int -- y:Int }\n"
        "  x x *\n"
        ";"
    )

    first_x = program.words[0].body.items[0]
    assert first_x.resolution.qualified_name == "local:x"


def test_resolve_if_blocks():
    program = resolve_source(
        ": abs { x:Int -- y:Int }\n"
        "  x 0 < if\n"
        "    0 x -\n"
        "  else\n"
        "    x\n"
        "  end\n"
        ";"
    )

    if_node = program.words[0].body.items[3]
    assert isinstance(if_node, IfNode)
    assert if_node.then_block.items[1].resolution.qualified_name == "local:x"
    assert if_node.else_block.items[0].resolution.qualified_name == "local:x"


def test_resolve_case_pattern_bindings():
    program = resolve_source(
        ": f { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Ok(v) => v\n"
        "    Err(e) => 0\n"
        "  end\n"
        ";"
    )

    case_node = program.words[0].body.items[1]
    ok_branch = case_node.branches[0]
    assert ok_branch.body.items[0].resolution.qualified_name == "local:v"


@pytest.mark.parametrize("variant_name", ["OutOfBounds", "MissingKey"])
def test_resolve_err_variant_pattern_does_not_create_local(variant_name):
    program = resolve_source(
        ": f { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        f"    Err({variant_name}) => 0\n"
        "  end\n"
        ";"
    )

    case_node = program.words[0].body.items[1]
    branch = case_node.branches[0]
    assert branch.pattern.kind is PatternKind.ERR
    assert branch.pattern.value == variant_name
    assert branch.pattern.binding is None


def test_resolve_err_binding_pattern_still_creates_local():
    program = resolve_source(
        ": f { r:Result<Int,MapError> -- n:Int }\n"
        "  r case\n"
        "    Err(e) => e\n"
        "  end\n"
        ";"
    )

    case_node = program.words[0].body.items[1]
    branch = case_node.branches[0]
    assert branch.pattern.kind is PatternKind.ERR
    assert branch.pattern.binding == "e"
    assert branch.body.items[0].resolution.qualified_name == "local:e"


def test_resolve_quote_locals():
    program = resolve_source(
        ": q { -- }\n"
        "  :[ | x:Int -- y:Int | x 1 + ;]\n"
        ";"
    )

    quote = program.words[0].body.items[0]
    assert isinstance(quote, QuoteNode)
    assert quote.body.items[0].resolution.qualified_name == "local:x"


def test_resolve_host_reference_with_contract():
    signature = signature_from_source(": hostsig { msg:String -- } ;")
    program = resolve_source_with_host_contract(
        ": log { msg:String -- }\n"
        "  msg host.log\n"
        ";",
        [HostWord(name="host.log", signature=signature, effect=HostEffect.PURE)],
    )

    host_ref = program.words[0].body.items[1]
    assert host_ref.resolution.owner_scope == "host"
    assert host_ref.resolution.qualified_name == "host.log"
    assert host_ref.resolution.resolved_symbol is not None
    assert host_ref.resolution.signature_reference is signature
    assert host_ref.resolution.host_effect is HostEffect.PURE


def test_resolve_host_reference_with_dirty_effect_metadata():
    signature = signature_from_source(": hostsig { msg:String -- } ;")
    program = resolve_source_with_host_contract(
        ": log { msg:String -- }\n"
        "  msg host.log\n"
        ";",
        [HostWord(name="host.log", signature=signature, effect=HostEffect.DIRTY)],
    )

    host_ref = program.words[0].body.items[1]
    assert host_ref.resolution.owner_scope == "host"
    assert host_ref.resolution.qualified_name == "host.log"
    assert host_ref.resolution.host_effect is HostEffect.DIRTY


def test_resolve_required_host_reference_with_contract():
    signature = signature_from_source(": hostsig { msg:String -- } ;")
    program = resolve_source_with_host_contract(
        ": log { msg:String -- }\n"
        "  msg host.log\n"
        ";",
        [HostWord(name="host.log", signature=signature, availability=BindingAvailability.REQUIRED, effect=HostEffect.PURE)],
    )

    host_ref = program.words[0].body.items[1]
    assert host_ref.resolution.owner_scope == "host"
    assert host_ref.resolution.qualified_name == "host.log"


def test_resolve_host_reference_without_contract_rejected():
    with pytest.raises(ResolutionError, match="host contract required for host\\.\\* reference"):
        resolve_source(
            ": log { msg:String -- }\n"
            "  msg host.log\n"
            ";"
        )


def test_resolve_missing_host_word_rejected():
    with pytest.raises(ResolutionError, match="unknown host word"):
        resolve_source_with_host_contract(
            ": log { msg:String -- }\n"
            "  msg host.missing\n"
            ";",
            [],
        )


def test_resolve_optional_host_word_direct_call_rejected():
    signature = signature_from_source(": hostsig { msg:String -- } ;")
    with pytest.raises(ResolutionError, match="optional host word cannot be called directly in v1"):
        resolve_source_with_host_contract(
            ": log { msg:String -- }\n"
            "  msg host.log\n"
            ";",
            [HostWord(name="host.log", signature=signature, availability=BindingAvailability.OPTIONAL, effect=HostEffect.PURE)],
        )


def test_resolve_unknown_name_raises():
    with pytest.raises(ResolutionError):
        resolve_source(
            ": main { -- }\n"
            "  does-not-exist\n"
            ";"
        )


def test_resolve_builtin_list_get_after_injection():
    program = resolve_source(
        ": main { xs:List<Int> -- r:Result<Int,ListError> }\n"
        "  xs 0 list.get\n"
        ";",
        with_builtins=True,
    )

    builtin_ref = program.words[0].body.items[2]
    assert builtin_ref.resolution.resolved_symbol is not None
    assert builtin_ref.resolution.resolved_symbol.name == "list.get"
    assert builtin_ref.resolution.resolved_symbol.source.name == "BUILTIN"


def test_resolve_builtin_map_set_after_injection():
    program = resolve_source(
        ': main { m:Map<String,Int> -- m2:Map<String,Int> }\n'
        '  m "k" 1 map.set\n'
        ";",
        with_builtins=True,
    )

    builtin_ref = program.words[0].body.items[3]
    assert builtin_ref.resolution.resolved_symbol is not None
    assert builtin_ref.resolution.resolved_symbol.name == "map.set"
    assert builtin_ref.resolution.resolved_symbol.source.name == "BUILTIN"


def test_list_get_remains_unresolved_without_injection():
    with pytest.raises(ResolutionError):
        resolve_source(
            ": main { xs:List<Int> -- r:Result<Int,ListError> }\n"
            "  xs 0 list.get\n"
            ";"
        )
