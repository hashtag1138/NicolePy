from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nicole.ast_nodes import CaseNode, IdentifierNode, IfNode, ModuleDeclaration, QuoteNode, WordDefNode
from nicole.checker import Checker, CheckerError, check_program
from nicole.errors import DiagnosticPhase
from nicole.host_abi import HostABIError, HostEffect, HostOpaqueType, HostWord, host_contract_from_words
from nicole.lexer import lex
from nicole.parser import Parser
from nicole.resolver import resolve
from nicole.source import MEMORY_SOURCE_PATH, SYNTHETIC_SOURCE_PATH
from nicole.signature_collector import collect_signatures
from nicole.standard_symbols import with_standard_symbols

def _parse_source(source: str):
    return Parser(lex(source)).parse()

def get_module_word(program, *, module_name: str, word_name: str) -> WordDefNode:
    for declaration in program.declarations:
        if not isinstance(declaration, ModuleDeclaration):
            continue
        if '.'.join(declaration.name.parts) != module_name:
            continue
        for item in declaration.items:
            if isinstance(item, WordDefNode) and item.name == word_name:
                return item
    raise AssertionError(f"word '{word_name}' not found in module '@{module_name}'")

def check_source(source: str):
    program = _parse_source(source)
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
    resolved = resolve(program, symbols)
    return check_program(resolved, symbols)

def signature_from_source(source: str):
    program = _parse_source(source)
    return program.words[0].signature

def _opaque_types(type_names):
    return [HostOpaqueType(name=type_name) for type_name in type_names]


def check_source_with_host_contract(source: str, host_words, *, opaque_type_names=()):
    program = _parse_source(source)
    symbols = collect_signatures(program)
    symbols = with_standard_symbols(symbols)
    contract = host_contract_from_words(
        host_words,
        opaque_types=_opaque_types(opaque_type_names),
    )
    resolved = resolve(program, symbols, host_contract=contract)
    return check_program(
        resolved,
        symbols,
        declared_opaque_type_names=frozenset(contract.opaque_types),
    )

def check_source_without_builtins(source: str):
    program = _parse_source(source)
    symbols = collect_signatures(program)
    resolved = resolve(program, symbols)
    return check_program(resolved, symbols)

def check_source_with_host_contract_without_builtins(source: str, host_words, *, opaque_type_names=()):
    program = _parse_source(source)
    symbols = collect_signatures(program)
    contract = host_contract_from_words(
        host_words,
        opaque_types=_opaque_types(opaque_type_names),
    )
    resolved = resolve(program, symbols, host_contract=contract)
    return check_program(
        resolved,
        symbols,
        declared_opaque_type_names=frozenset(contract.opaque_types),
    )

def _marked_calls(block) -> list[IdentifierNode]:
    marked: list[IdentifierNode] = []
    for item in block.items:
        if isinstance(item, IdentifierNode) and item.resolution.is_self_tail_call:
            marked.append(item)
            continue
        if isinstance(item, IfNode):
            marked.extend(_marked_calls(item.then_block))
            marked.extend(_marked_calls(item.else_block))
            continue
        if isinstance(item, CaseNode):
            for branch in item.branches:
                if branch.guard is not None:
                    marked.extend(_marked_calls(branch.guard))
                marked.extend(_marked_calls(branch.body))
            continue
        if isinstance(item, QuoteNode):
            marked.extend(_marked_calls(item.body))
    return marked


def _find_identifier(block, name: str) -> IdentifierNode:
    for item in block.items:
        if isinstance(item, IdentifierNode) and item.name == name:
            return item
        if isinstance(item, IfNode):
            try:
                return _find_identifier(item.then_block, name)
            except AssertionError:
                pass
            try:
                return _find_identifier(item.else_block, name)
            except AssertionError:
                pass
        if isinstance(item, CaseNode):
            for branch in item.branches:
                if branch.guard is not None:
                    try:
                        return _find_identifier(branch.guard, name)
                    except AssertionError:
                        pass
                try:
                    return _find_identifier(branch.body, name)
                except AssertionError:
                    pass
        if isinstance(item, QuoteNode):
            try:
                return _find_identifier(item.body, name)
            except AssertionError:
                pass
    raise AssertionError(f"identifier '{name}' not found")

def test_checker_accepts_simple_add():
    check_source('module @app\n  : add { x:Int y:Int -- z:Int }\n    x y +\n  ;\nend-module\n')

def test_checker_accepts_explicit_module_program() -> None:
    check_source('module @calc\n  : add { x:Int y:Int -- z:Int }\n    x y +\n  ;\nend-module')

def test_checker_accepts_v1_primitive_signature_types() -> None:
    check_source('module @app\n  : id { i:Int f:Float b:Bool s:String u:Unit -- i2:Int f2:Float b2:Bool s2:String u2:Unit }\n    i f b s u\n  ;\nend-module\n')

def test_checker_accepts_v1_nested_container_types() -> None:
    check_source('module @app\n  : pass { xs:List<Result<Int,Bool>> m:Map<String,List<Result<Int,Bool>>> -- ys:List<Result<Int,Bool>> out:Map<String,List<Result<Int,Bool>>> }\n    xs m\n  ;\nend-module\n')

def test_checker_rejects_unknown_nominal_type_in_signature() -> None:
    with pytest.raises(CheckerError, match='type is not supported in v1: Foo') as exc_info:
        check_source('module @app\n  : id { x:Foo -- y:Foo }\n    x\n  ;\nend-module\n')

    error = exc_info.value
    assert not isinstance(error, HostABIError)
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_UNSUPPORTED_TYPE_V1"

def test_checker_rejects_nested_unknown_nominal_type() -> None:
    with pytest.raises(CheckerError, match='type is not supported in v1: CustomError'):
        check_source('module @app\n  : bad { x:Result<Int,CustomError> -- }\n    x drop\n  ;\nend-module\n')

def test_checker_accepts_declared_opaque_type_in_word_signature() -> None:
    check_source_with_host_contract(
        'module @app\n  : id { fh:host.io.FileHandle -- out:host.io.FileHandle }\n    fh\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_local_declaration() -> None:
    check_source_with_host_contract(
        'module @app\n  : local-use { fh:host.io.FileHandle -- out:host.io.FileHandle }\n    fh\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_stack_flow() -> None:
    check_source_with_host_contract(
        'module @app\n  : flow { fh:host.io.FileHandle -- out:host.io.FileHandle }\n    fh dup drop\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_list() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { xs:List<host.io.FileHandle> -- ys:List<host.io.FileHandle> }\n    xs\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_result_value() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { r:Result<host.io.FileHandle,String> -- out:Result<host.io.FileHandle,String> }\n    r\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_result_error() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { r:Result<String,host.io.FileHandle> -- out:Result<String,host.io.FileHandle> }\n    r\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_quotation_signature() -> None:
    check_source_with_host_contract(
        'module @app\n  : make-q { fh:host.io.FileHandle -- q:Quote<{ captured:host.io.FileHandle | x:host.io.FileHandle -- y:host.io.FileHandle }> }\n    fh\n    :[ captured:host.io.FileHandle | x:host.io.FileHandle -- y:host.io.FileHandle |\n      x\n    ;]\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_map_string_value() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { m:Map<String,host.io.FileHandle> -- out:Map<String,host.io.FileHandle> }\n    m\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_map_int_value() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { m:Map<Int,host.io.FileHandle> -- out:Map<Int,host.io.FileHandle> }\n    m\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_accepts_declared_opaque_type_in_map_bool_value() -> None:
    check_source_with_host_contract(
        'module @app\n  : keep { m:Map<Bool,host.io.FileHandle> -- out:Map<Bool,host.io.FileHandle> }\n    m\n  ;\nend-module\n',
        [],
        opaque_type_names=('host.io.FileHandle',),
    )


def test_checker_rejects_undeclared_host_opaque_type() -> None:
    with pytest.raises(CheckerError, match='undeclared host opaque type in checker: host.io.FileHandle'):
        check_source_with_host_contract(
            'module @app\n  : bad { -- fh:host.io.FileHandle }\n  ;\nend-module\n',
            [],
            opaque_type_names=('host.net.TcpSocket',),
        )


def test_checker_rejects_declared_opaque_type_as_map_key() -> None:
    with pytest.raises(CheckerError, match='Map<K,V> key type must be Int, String, or Bool in v1'):
        check_source_with_host_contract(
            'module @app\n  : bad { -- m:Map<host.io.FileHandle,String> }\n    map.empty:Map<host.io.FileHandle,String>\n  ;\nend-module\n',
            [],
            opaque_type_names=('host.io.FileHandle',),
        )


@pytest.mark.parametrize('operator', ['=', '!='])
def test_checker_rejects_equality_on_declared_opaque_type(operator: str) -> None:
    with pytest.raises(CheckerError, match='equality is not supported for host opaque types'):
        check_source_with_host_contract(
            f'module @app\n  : bad {{ x:host.io.FileHandle y:host.io.FileHandle -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n',
            [],
            opaque_type_names=('host.io.FileHandle',),
        )


def test_checker_accepts_host_word_with_matching_signature():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  : main { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.PURE)])

def test_checker_rejects_host_word_with_wrong_input_type():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError):
        check_source_with_host_contract('module @app\n  : main { n:Int -- }\n    n host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.PURE)])

def test_checker_accepts_host_word_with_output():
    host_signature = signature_from_source('module @app\n  : hostsig { -- n:Int } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  : main { -- n:Int }\n    host.random-int\n  ;\nend-module\n', [HostWord(name='host.random-int', signature=host_signature, effect=HostEffect.PURE)])

def test_checker_rejects_obvious_type_mismatch():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- y:Int }\n    x "hello" +\n  ;\nend-module\n')

def test_checker_rejects_stack_underflow():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- y:Int }\n    +\n  ;\nend-module\n')

def test_checker_rejects_drop_at_word_start_even_with_inputs():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- }\n    drop\n  ;\nend-module\n')

def test_checker_rejects_extra_final_value():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : weird { x:Int y:Int -- z:Int }\n    1\n    x y +\n  ;\nend-module\n')

def test_checker_accepts_valid_if():
    check_source('module @app\n  : abs { x:Int -- y:Int }\n    x 0 < if\n      0 x -\n    else\n      x\n    end\n  ;\nend-module\n')

def test_checker_rejects_if_branch_type_mismatch():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- y:Int }\n    x 0 < if\n      1\n    else\n      "hello"\n    end\n  ;\nend-module\n')

def test_checker_rejects_non_bool_if_condition():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- y:Int }\n    x if\n      1\n    else\n      2\n    end\n  ;\nend-module\n')

def test_checker_accepts_simple_bool_case():
    check_source('module @app\n  : choose { b:Bool -- n:Int }\n    b case\n      true => 1\n      false => 0\n    end\n  ;\nend-module\n')

def test_checker_case_consumes_scrutinee():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { b:Bool -- b2:Bool n:Int }\n    b case\n      true => 1\n      false => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_case_branch_arity_mismatch():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { b:Bool -- n:Int }\n    b case\n      true => 1\n      false => 1 2\n    end\n  ;\nend-module\n')

def test_checker_rejects_case_branch_type_mismatch():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { b:Bool -- n:Int }\n    b case\n      true => 1\n      false => "no"\n    end\n  ;\nend-module\n')

def test_checker_case_ok_pattern_binds_local():
    check_source('module @app\n  : unwrap { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v\n      Err(MissingKey) => 0\n    end\n  ;\nend-module\n')

def test_checker_drop_in_case_branch_uses_branch_stack():
    check_source('module @app\n  : ignore-ok { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v drop 0\n      Err(MissingKey) => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_non_exhaustive_bool_case():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { b:Bool -- n:Int }\n    b case\n      true => 1\n    end\n  ;\nend-module\n')

def test_checker_accepts_exhaustive_bool_case():
    check_source('module @app\n  : ok { b:Bool -- n:Int }\n    b case\n      true => 1\n      false => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_bool_case_with_wildcard():
    check_source('module @app\n  : ok { b:Bool -- n:Int }\n    b case\n      true => 1\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_case_guard_with_bool_result() -> None:
    check_source('module @app\n  : classify { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when v 0 > => v\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_case_guard_that_is_not_bool() -> None:
    with pytest.raises(CheckerError, match='case guard must produce Bool'):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when v => v\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_case_guard_with_extra_stack_values() -> None:
    with pytest.raises(CheckerError, match='case guard must produce exactly one Bool'):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when true true => v\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_case_guard_consuming_preexisting_stack() -> None:
    with pytest.raises(CheckerError, match='case guard must not consume preexisting stack values'):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when dup true => v\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_dirty_call_in_case_guard() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='case guard cannot call dirty code'):
        check_source_with_host_contract('module @app\n  dirty : use-guard { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when "x" host.log true => v\n      _ => 0\n    end\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_rejects_propagate_in_case_guard() -> None:
    with pytest.raises(CheckerError, match='case guard cannot contain \\?'):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) when map.empty:Map<String,Int> "k" map.get ? => v\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_guarded_wildcard_is_not_exhaustive() -> None:
    with pytest.raises(CheckerError, match='case is not exhaustive'):
        check_source('module @app\n  : bad { b:Bool -- n:Int }\n    b case\n      _ when true => 1\n    end\n  ;\nend-module\n')

def test_checker_unguarded_wildcard_remains_exhaustive_with_guarded_branch() -> None:
    check_source('module @app\n  : ok { b:Bool -- n:Int }\n    b case\n      true when false => 1\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_non_exhaustive_result_map_error_case():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v\n    end\n  ;\nend-module\n')

def test_checker_rejects_result_map_error_case_with_err_only():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Err(MissingKey) => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_exhaustive_map_error_single_variant_case():
    check_source('module @app\n  : ok { e:MapError -- n:Int }\n    e case\n      MissingKey => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_exhaustive_map_error_case_with_wildcard():
    check_source('module @app\n  : ok { e:MapError -- n:Int }\n    e case\n      MissingKey => 0\n      _ => 1\n    end\n  ;\nend-module\n')

def test_checker_accepts_exhaustive_list_error_single_variant_case():
    check_source('module @app\n  : ok { e:ListError -- n:Int }\n    e case\n      OutOfBounds => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_exhaustive_list_error_case_with_wildcard():
    check_source('module @app\n  : ok { e:ListError -- n:Int }\n    e case\n      OutOfBounds => 0\n      _ => 1\n    end\n  ;\nend-module\n')

def test_checker_accepts_result_map_error_case_with_specific_err_variant():
    check_source('module @app\n  : ok { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v\n      Err(MissingKey) => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_result_map_error_case_with_err_binding():
    check_source('module @app\n  : ok { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v\n      Err(e) => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_missing_key_pattern_in_bool_case():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { b:Bool -- n:Int }\n    b case\n      MissingKey => 1\n      _ => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_missing_key_variant_for_list_error_result():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { r:Result<Int,ListError> -- n:Int }\n    r case\n      Ok(v) => v\n      Err(MissingKey) => 0\n    end\n  ;\nend-module\n')

def test_checker_rejects_out_of_bounds_variant_for_map_error_result():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { r:Result<Int,MapError> -- n:Int }\n    r case\n      Ok(v) => v\n      Err(OutOfBounds) => 0\n    end\n  ;\nend-module\n')

def test_checker_accepts_typed_empty_list_value():
    check_source('module @app\n  : empty-list { -- xs:List<Int> }\n    []:List<Int>\n  ;\nend-module\n')

def test_checker_accepts_typed_empty_map_value():
    check_source('module @app\n  : empty-map { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n  ;\nend-module\n')

def test_checker_accepts_map_with_valid_string_key_type() -> None:
    check_source('module @app\n  : ok { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n  ;\nend-module\n')

def test_checker_accepts_map_with_valid_bool_key_type_and_nested_value() -> None:
    check_source('module @app\n  : ok { -- m:Map<Bool,List<Int>> }\n    map.empty:Map<Bool,List<Int>>\n  ;\nend-module\n')

def test_checker_rejects_map_with_list_key_type() -> None:
    with pytest.raises(CheckerError, match='Map<K,V> key type must be Int, String, or Bool in v1'):
        check_source('module @app\n  : bad { -- m:Map<List<Int>,Int> }\n    map.empty:Map<List<Int>,Int>\n  ;\nend-module\n')

def test_checker_rejects_map_with_result_key_type() -> None:
    with pytest.raises(CheckerError, match='Map<K,V> key type must be Int, String, or Bool in v1'):
        check_source('module @app\n  : bad { -- m:Map<Result<Int,MapError>,Int> }\n    map.empty:Map<Result<Int,MapError>,Int>\n  ;\nend-module\n')

def test_checker_rejects_map_with_float_key_type() -> None:
    with pytest.raises(CheckerError, match='Map<K,V> key type must be Int, String, or Bool in v1'):
        check_source('module @app\n  : bad-float-key { -- m:Map<Float,Int> }\n    map.empty:Map<Float,Int>\n  ;\nend-module\n')

def test_checker_rejects_map_with_quote_key_type() -> None:
    with pytest.raises(CheckerError, match='Map<K,V> key type must be Int, String, or Bool in v1'):
        check_source('module @app\n  : bad-quote-key { -- m:Map<Quote<{ | -- }>,Int> }\n    map.empty:Map<Quote<{ | -- }>,Int>\n  ;\nend-module\n')

def test_checker_rejects_typed_empty_list_with_wrong_return_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- xs:List<String> }\n    []:List<Int>\n  ;\nend-module\n')

def test_checker_rejects_typed_empty_map_with_wrong_return_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- m:Map<String,String> }\n    map.empty:Map<String,Int>\n  ;\nend-module\n')

def test_checker_accepts_drop_after_typed_empty_list():
    check_source('module @app\n  : ignore { -- }\n    []:List<Int> drop\n  ;\nend-module\n')

def test_checker_accepts_list_len_builtin():
    check_source('module @app\n  : len { -- n:Int }\n    []:List<Int> list.len\n  ;\nend-module\n')

def test_checker_accepts_list_is_empty_builtin():
    check_source('module @app\n  : empty { -- b:Bool }\n    []:List<Int> list.is-empty\n  ;\nend-module\n')

def test_checker_accepts_list_first_and_last_builtins():
    check_source('module @app\n  : first-last { -- a:Result<Int,ListError> b:Result<Int,ListError> }\n    [4, 9] list.first\n    [4, 9] list.last\n  ;\nend-module\n')

def test_checker_accepts_list_append_and_reverse_builtins():
    check_source('module @app\n  : append-reverse { -- xs:List<Int> }\n    [1, 2] 3 list.append list.reverse\n  ;\nend-module\n')

def test_checker_accepts_map_len_builtin():
    check_source('module @app\n  : len { -- n:Int }\n    map.empty:Map<String,Int> map.len\n  ;\nend-module\n')

def test_checker_accepts_map_is_empty_builtin():
    check_source('module @app\n  : empty { -- b:Bool }\n    map.empty:Map<String,Int> map.is-empty\n  ;\nend-module\n')

def test_checker_accepts_map_keys_and_values_builtins():
    check_source('module @app\n  : kv { -- ks:List<String> vs:List<Int> }\n    map.empty:Map<String,Int> map.keys\n    map.empty:Map<String,Int> map.values\n  ;\nend-module\n')

def test_checker_rejects_list_len_on_non_list():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    1 list.len\n  ;\nend-module\n')

def test_checker_rejects_map_len_on_non_map():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    1 map.len\n  ;\nend-module\n')

def test_checker_rejects_wrong_return_type_after_list_len():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- s:String }\n    []:List<Int> list.len\n  ;\nend-module\n')

def test_checker_accepts_map_contains_with_matching_key():
    check_source('module @app\n  : ok { -- b:Bool }\n    map.empty:Map<String,Int>\n    "hello"\n    map.contains\n  ;\nend-module\n')

def test_checker_rejects_map_contains_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- b:Bool }\n    map.empty:Map<String,Int>\n    42\n    map.contains\n  ;\nend-module\n')

def test_checker_rejects_map_contains_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- b:Bool }\n    1\n    "hello"\n    map.contains\n  ;\nend-module\n')

def test_checker_accepts_result_is_ok_builtin():
    check_source('module @app\n  : ok { -- b:Bool }\n    []:List<Int>\n    0\n    list.get\n    result.is-ok\n  ;\nend-module\n')

def test_checker_accepts_result_is_err_builtin():
    check_source('module @app\n  : ok { -- b:Bool }\n    []:List<Int>\n    0\n    list.get\n    result.is-err\n  ;\nend-module\n')

def test_checker_accepts_result_unwrap_or_builtin():
    check_source('module @app\n  : ok { -- n:Int }\n    []:List<Int>\n    0\n    list.get\n    42\n    result.unwrap-or\n  ;\nend-module\n')

def test_checker_accepts_ok_constructor_in_result_frame() -> None:
    check_source('module @app\n  : ok { -- r:Result<Int,MapError> }\n    1\n    Ok!\n  ;\nend-module\n')

def test_checker_accepts_err_constructor_in_result_frame() -> None:
    check_source('module @app\n  : err { e:MapError -- r:Result<Int,MapError> }\n    e\n    Err!\n  ;\nend-module\n')

def test_checker_accepts_err_constructor_with_non_string_error_type() -> None:
    check_source('module @app\n  : err { e:Int -- r:Result<Bool,Int> }\n    e\n    Err!\n  ;\nend-module\n')

def test_checker_accepts_propagate_with_matching_result_error_type() -> None:
    check_source('module @app\n  : ok { -- r:Result<Int,MapError> }\n    map.empty:Map<String,Int>\n    "k"\n    map.get\n    ?\n    1 +\n    Ok!\n  ;\nend-module\n')

def test_checker_accepts_propagate_inside_quotation_with_result_output() -> None:
    check_source('module @app\n  : q { -- q:Quote<{ | -- r:Result<Int,MapError> }> }\n    :[ | -- r:Result<Int,MapError> |\n      map.empty:Map<String,Int>\n      "k"\n      map.get\n      ?\n      1 +\n      Ok!\n    ;]\n  ;\nend-module\n')

def test_checker_accepts_nested_propagate_in_valid_contexts() -> None:
    check_source('module @app\n  : nested { -- r:Result<Int,MapError> }\n    map.empty:Map<String,Int>\n    "a"\n    map.get\n    ?\n    map.empty:Map<String,Int>\n    "b"\n    map.get\n    ?\n    +\n    Ok!\n  ;\nend-module\n')

def test_checker_rejects_ok_constructor_with_wrong_value_type() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,MapError> }\n    "bad"\n    Ok!\n  ;\nend-module\n')

def test_checker_rejects_err_constructor_with_wrong_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { e:ListError -- r:Result<Int,MapError> }\n    e\n    Err!\n  ;\nend-module\n')

def test_checker_rejects_ok_constructor_in_non_result_frame() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    1\n    Ok!\n  ;\nend-module\n')

def test_checker_rejects_err_constructor_in_non_result_frame() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { e:MapError -- n:Int }\n    e\n    Err!\n  ;\nend-module\n')

def test_checker_accepts_list_concat_with_matching_item_types():
    check_source('module @app\n  : xs { -- out:List<Int> }\n    []:List<Int>\n    []:List<Int>\n    list.concat\n  ;\nend-module\n')

def test_checker_accepts_list_filter_builtin() -> None:
    check_source('module @app\n  : filter { -- xs:List<Int> }\n    []:List<Int>\n    :[ | x:Int -- keep:Bool | true ;]\n    list.filter\n  ;\nend-module\n')

def test_checker_rejects_result_unwrap_or_with_wrong_fallback_type() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    []:List<Int>\n    0\n    list.get\n    "fallback"\n    result.unwrap-or\n  ;\nend-module\n')

def test_checker_rejects_propagate_on_non_result_input() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,MapError> }\n    1\n    ?\n    Ok!\n  ;\nend-module\n')

def test_checker_rejects_propagate_with_non_result_frame_output() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    map.empty:Map<String,Int>\n    "k"\n    map.get\n    ?\n  ;\nend-module\n')

def test_checker_rejects_propagate_with_multiple_frame_outputs() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- a:Int b:Int }\n    map.empty:Map<String,Int>\n    "k"\n    map.get\n    ?\n    1 2\n  ;\nend-module\n')

def test_checker_rejects_propagate_with_mismatched_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,MapError> }\n    []:List<Int>\n    0\n    list.get\n    ?\n    Ok!\n  ;\nend-module\n')

def test_checker_rejects_propagate_inside_quotation_with_non_result_output() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- q:Quote<{ | -- n:Int }> }\n    :[ | -- n:Int |\n      map.empty:Map<String,Int>\n      "k"\n      map.get\n      ?\n    ;]\n  ;\nend-module\n')

def test_checker_rejects_propagate_inside_quotation_with_mismatched_error_type() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- q:Quote<{ | -- r:Result<Int,MapError> }> }\n    :[ | -- r:Result<Int,MapError> |\n      []:List<Int>\n      0\n      list.get\n      ?\n      Ok!\n    ;]\n  ;\nend-module\n')

def test_checker_rejects_list_filter_with_non_bool_quote_output() -> None:
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- xs:List<Int> }\n    []:List<Int>\n    :[ | x:Int -- keep:Int | x ;]\n    list.filter\n  ;\nend-module\n')

def test_checker_rejects_list_concat_with_mismatched_item_types():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- out:List<Int> }\n    []:List<Int>\n    []:List<String>\n    list.concat\n  ;\nend-module\n')

def test_checker_accepts_list_get_builtin():
    check_source('module @app\n  : get { -- r:Result<Int,ListError> }\n    []:List<Int>\n    0\n    list.get\n  ;\nend-module\n')

def test_checker_rejects_list_get_with_non_int_index():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,ListError> }\n    []:List<Int>\n    "zero"\n    list.get\n  ;\nend-module\n')

def test_checker_accepts_list_set_builtin():
    check_source('module @app\n  : set { -- r:Result<List<Int>,ListError> }\n    []:List<Int>\n    0\n    1\n    list.set\n  ;\nend-module\n')

def test_checker_rejects_list_set_with_wrong_value_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<List<Int>,ListError> }\n    []:List<Int>\n    0\n    "x"\n    list.set\n  ;\nend-module\n')

def test_checker_rejects_list_set_with_non_int_index():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<List<Int>,ListError> }\n    []:List<Int>\n    "zero"\n    1\n    list.set\n  ;\nend-module\n')

def test_checker_rejects_list_set_with_non_list_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<List<Int>,ListError> }\n    1\n    0\n    2\n    list.set\n  ;\nend-module\n')

def test_checker_accepts_list_set_for_other_item_type():
    check_source('module @app\n  : set { -- r:Result<List<String>,ListError> }\n    []:List<String>\n    0\n    "x"\n    list.set\n  ;\nend-module\n')

def test_checker_accepts_map_get_builtin():
    check_source('module @app\n  : get { -- r:Result<Int,MapError> }\n    map.empty:Map<String,Int>\n    "hello"\n    map.get\n  ;\nend-module\n')

def test_checker_rejects_map_get_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,MapError> }\n    map.empty:Map<String,Int>\n    42\n    map.get\n  ;\nend-module\n')

def test_checker_rejects_map_get_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Int,MapError> }\n    1\n    "hello"\n    map.get\n  ;\nend-module\n')

def test_checker_accepts_map_set_builtin():
    check_source('module @app\n  : set { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n    "hello"\n    1\n    map.set\n  ;\nend-module\n')

def test_checker_rejects_map_set_with_wrong_value_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n    "hello"\n    "wrong"\n    map.set\n  ;\nend-module\n')

def test_checker_rejects_map_set_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- m:Map<String,Int> }\n    "not-a-map"\n    "hello"\n    1\n    map.set\n  ;\nend-module\n')

def test_checker_rejects_map_set_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n    42\n    1\n    map.set\n  ;\nend-module\n')

def test_checker_accepts_map_remove_builtin():
    check_source('module @app\n  : remove { -- r:Result<Map<String,Int>,MapError> }\n    map.empty:Map<String,Int>\n    "hello"\n    map.remove\n  ;\nend-module\n')

def test_checker_rejects_map_remove_with_wrong_key_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- m:Map<String,Int> }\n    map.empty:Map<String,Int>\n    42\n    map.remove\n  ;\nend-module\n')

def test_checker_rejects_map_remove_with_non_map_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- r:Result<Map<String,Int>,MapError> }\n    "not-a-map"\n    "hello"\n    map.remove\n  ;\nend-module\n')

def test_checker_rejects_wrong_return_type_after_list_get():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- s:String }\n    []:List<Int>\n    0\n    list.get\n  ;\nend-module\n')

def test_checker_accepts_simple_quotation_value():
    check_source('module @app\n  : make { -- q:Quote<{ | x:Int -- y:Int }> }\n    :[ | x:Int -- y:Int | x 1 + ;]\n  ;\nend-module\n')

def test_checker_accepts_quotation_with_capture():
    check_source('module @app\n  : make { -- q:Quote<{ captured:Int | value:Int -- out:Int }> }\n    10\n    :[ captured:Int | value:Int -- out:Int | captured value + ;]\n  ;\nend-module\n')

def test_checker_accepts_quotation_capture_reusing_parent_local_name():
    check_source('module @app\n  : add-offset { x:Int offset:Int -- y:Int }\n    offset\n    :[ offset:Int | value:Int -- out:Int | value offset + ;]\n    x\n    swap\n    call\n  ;\nend-module\n')

def test_checker_accepts_call_with_capture():
    check_source('module @app\n  : add10 { x:Int -- y:Int }\n    x\n    10\n    :[ captured:Int | value:Int -- out:Int | captured value + ;]\n    call\n  ;\nend-module\n')

def test_checker_rejects_quotation_with_extra_return_value():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- q:Quote<{ | x:Int -- y:Int }> }\n    :[ | x:Int -- y:Int | x x ;]\n  ;\nend-module\n')

def test_checker_rejects_drop_at_start_of_quotation():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- q:Quote<{ | x:Int -- y:Int }> }\n    :[ | x:Int -- y:Int | drop x ;]\n  ;\nend-module\n')

def test_checker_rejects_call_with_wrong_input_order():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- out:Int }\n    "hello"\n    1\n    :[ | a:Int b:String -- out:Int | a ;]\n    call\n  ;\nend-module\n')

def test_checker_rejects_call_on_non_quotation():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- out:Int }\n    1\n    call\n  ;\nend-module\n')

def test_checker_accepts_dup():
    check_source('module @app\n  : ok { x:Int -- a:Int b:Int }\n    x dup\n  ;\nend-module\n')

def test_checker_accepts_swap():
    check_source('module @app\n  : ok { x:Int y:String -- a:String b:Int }\n    x y swap\n  ;\nend-module\n')

def test_checker_accepts_over():
    check_source('module @app\n  : ok { x:Int y:String -- a:Int b:String c:Int }\n    x y over\n  ;\nend-module\n')

def test_checker_accepts_rot():
    check_source('module @app\n  : ok { x:Int y:String z:Bool -- a:String b:Bool c:Int }\n    x y z rot\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['dup', 'swap', 'over', 'rot'])
def test_checker_rejects_stack_underflow_for_stack_primitive(operator):
    with pytest.raises(CheckerError):
        check_source(f'module @app\n  : bad {{ -- }}\n    {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['-', '*', 'div', 'mod'])
def test_checker_accepts_integer_arithmetic_primitives(operator):
    check_source(f'module @app\n  : ok {{ x:Int y:Int -- z:Int }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['-', '*', 'div', 'mod'])
def test_checker_rejects_integer_arithmetic_with_wrong_type(operator):
    with pytest.raises(CheckerError):
        check_source(f'module @app\n  : bad {{ x:Int y:String -- z:Int }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['+.', '*.', '/.'])
def test_checker_accepts_float_arithmetic_primitives(operator):
    check_source(f'module @app\n  : ok {{ x:Float y:Float -- z:Float }}\n    x y {operator}\n  ;\nend-module\n')

def test_checker_rejects_float_arithmetic_with_mixed_types():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int y:Float -- z:Float }\n    x y +.\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['<', '<=', '>', '>='])
def test_checker_accepts_integer_comparisons(operator):
    check_source(f'module @app\n  : ok {{ x:Int y:Int -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['<', '<=', '>', '>='])
def test_checker_accepts_float_comparisons(operator):
    check_source(f'module @app\n  : ok {{ x:Float y:Float -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['<', '<=', '>', '>='])
def test_checker_rejects_non_int_order_comparisons(operator):
    with pytest.raises(CheckerError):
        check_source(f'module @app\n  : bad {{ x:String y:String -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n')

def test_checker_rejects_mixed_numeric_order_comparison():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int y:Float -- b:Bool }\n    x y <\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['=', '!='])
def test_checker_accepts_equality_for_same_types(operator):
    check_source(f'module @app\n  : ok {{ x:String y:String -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['=', '!='])
def test_checker_rejects_equality_for_different_types(operator):
    with pytest.raises(CheckerError):
        check_source(f'module @app\n  : bad {{ x:Int y:String -- b:Bool }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['and', 'or'])
def test_checker_accepts_boolean_binary_primitives(operator):
    check_source(f'module @app\n  : ok {{ x:Bool y:Bool -- z:Bool }}\n    x y {operator}\n  ;\nend-module\n')

@pytest.mark.parametrize('operator', ['and', 'or'])
def test_checker_rejects_boolean_binary_primitives_with_wrong_type(operator):
    with pytest.raises(CheckerError):
        check_source(f'module @app\n  : bad {{ x:Bool y:Int -- z:Bool }}\n    x y {operator}\n  ;\nend-module\n')

def test_checker_accepts_not():
    check_source('module @app\n  : ok { x:Bool -- y:Bool }\n    x not\n  ;\nend-module\n')

def test_checker_rejects_not_with_wrong_type():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { x:Int -- y:Bool }\n    x not\n  ;\nend-module\n')

def test_checker_rejects_not_with_underflow():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- y:Bool }\n    not\n  ;\nend-module\n')

def test_checker_accepts_non_empty_int_list_literal():
    check_source('module @app\n  : ints { -- xs:List<Int> }\n    [1, 2]\n  ;\nend-module\n')

def test_checker_accepts_non_empty_string_list_literal():
    check_source('module @app\n  : strings { -- xs:List<String> }\n    ["a", "b"]\n  ;\nend-module\n')

def test_checker_accepts_non_empty_bool_list_literal():
    check_source('module @app\n  : bools { -- xs:List<Bool> }\n    [true, false]\n  ;\nend-module\n')

def test_checker_rejects_heterogeneous_list_literal():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- xs:List<Int> }\n    [1, "x"]\n  ;\nend-module\n')

def test_checker_rejects_wrong_return_type_for_non_empty_list_literal():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- xs:List<String> }\n    [1, 2]\n  ;\nend-module\n')

def test_checker_accepts_drop_after_non_empty_list_literal():
    check_source('module @app\n  : ok { -- }\n    [1, 2] drop\n  ;\nend-module\n')

def test_checker_accepts_list_map_int_to_int():
    check_source('module @app\n  : inc-all { xs:List<Int> -- ys:List<Int> }\n    xs\n    :[ | x:Int -- y:Int | x 1 + ;]\n    list.map\n  ;\nend-module\n')

def test_checker_accepts_list_map_int_to_string():
    check_source('module @app\n  : label-all { xs:List<Int> -- ys:List<String> }\n    xs\n    :[ | x:Int -- y:String | "ok" ;]\n    list.map\n  ;\nend-module\n')

def test_checker_accepts_list_fold_sum():
    check_source('module @app\n  : sum { xs:List<Int> -- n:Int }\n    xs\n    0\n    :[ | acc:Int x:Int -- out:Int | acc x + ;]\n    list.fold\n  ;\nend-module\n')

def test_checker_accepts_list_reduce_int():
    check_source('module @app\n  : reduce { xs:List<Int> -- n:Int }\n    xs\n    :[ | a:Int b:Int -- c:Int | a b + ;]\n    list.reduce\n  ;\nend-module\n')

def test_checker_rejects_list_reduce_on_provably_empty_list():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { -- n:Int }\n    []:List<Int>\n    :[ | a:Int b:Int -- c:Int |\n      a b +\n    ;]\n    list.reduce\n  ;\nend-module\n')

def test_checker_accepts_list_reduce_on_non_empty_list_literal():
    check_source('module @app\n  : ok { -- n:Int }\n    [1, 2]\n    :[ | a:Int b:Int -- c:Int |\n      a b +\n    ;]\n    list.reduce\n  ;\nend-module\n')

def test_checker_rejects_list_map_with_incompatible_quotation_input():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { xs:List<Int> -- ys:List<Int> }\n    xs\n    :[ | x:String -- y:Int | 1 ;]\n    list.map\n  ;\nend-module\n')

def test_checker_rejects_list_map_with_two_outputs():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { xs:List<Int> -- ys:List<Int> }\n    xs\n    :[ | x:Int -- y:Int z:Int | x x ;]\n    list.map\n  ;\nend-module\n')

def test_checker_rejects_list_fold_with_incompatible_accumulator():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { xs:List<Int> -- n:Int }\n    xs\n    "zero"\n    :[ | acc:Int x:Int -- out:Int | acc x + ;]\n    list.fold\n  ;\nend-module\n')

def test_checker_rejects_list_reduce_with_incompatible_output():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { xs:List<Int> -- n:Int }\n    xs\n    :[ | a:Int b:Int -- c:String | "no" ;]\n    list.reduce\n  ;\nend-module\n')

def test_checker_rejects_list_map_with_non_quotation_argument():
    with pytest.raises(CheckerError):
        check_source('module @app\n  : bad { xs:List<Int> -- ys:List<Int> }\n    xs\n    1\n    list.map\n  ;\nend-module\n')

def test_checker_phase4_pure_implicit_passes():
    check_source('module @app\n  : helper { -- n:Int }\n    1\n  ;\n  : main { -- n:Int }\n    helper\n  ;\nend-module\n')

def test_checker_phase4_dirty_explicit_passes():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : write-log { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_rejects_missing_dirty_for_direct_host_source():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  : write-log { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_rejects_redundant_dirty_annotation():
    with pytest.raises(CheckerError, match='annotated dirty.*inferred pure'):
        check_source('module @app\n  dirty : no-side-effect { -- n:Int }\n    1\n  ;\nend-module\n')

def test_checker_phase4_host_pure_source_remains_pure():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  : write-log { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.PURE)])

def test_checker_phase4_transitive_dirty_propagation_passes_with_annotations():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : leaf { msg:String -- }\n    msg host.log\n  ;\n  dirty : middle { msg:String -- }\n    msg leaf\n  ;\n  dirty : root { msg:String -- }\n    msg middle\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_allows_pure_self_recursion_without_dirty_source():
    check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n 0 = if\n      n\n    else\n      n 1 - loop\n    end\n  ;\nend-module\n')

def test_checker_phase4_allows_pure_mutual_recursion_without_dirty_source():
    check_source('module @app\n  : even { n:Int -- b:Bool }\n    n 0 = if\n      true\n    else\n      n 1 - odd\n    end\n  ;\n  : odd { n:Int -- b:Bool }\n    n 0 = if\n      false\n    else\n      n 1 - even\n    end\n  ;\nend-module\n')

def test_checker_marks_direct_self_call_in_final_position() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n 1 - loop\n  ;\nend-module\n')
    call = program.words[0].body.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is True
    assert _marked_calls(program.words[0].body) == [call]

def test_checker_does_not_mark_self_call_followed_by_other_operation() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n 1 - loop 1 +\n  ;\nend-module\n')
    call = program.words[0].body.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []

def test_checker_does_not_mark_self_call_followed_by_propagate() -> None:
    program = check_source('module @app\n  : loop { n:Int -- r:Result<Int,MapError> }\n    n 1 - loop ? Ok!\n  ;\nend-module\n')
    call = program.words[0].body.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []

def test_checker_marks_self_call_only_in_tail_branch_of_if() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n 0 = if\n      n\n    else\n      n 1 - loop\n    end\n  ;\nend-module\n')
    if_node = program.words[0].body.items[3]
    assert isinstance(if_node, IfNode)
    call = if_node.else_block.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is True
    assert _marked_calls(program.words[0].body) == [call]

def test_checker_does_not_mark_self_call_in_non_tail_branch_of_if() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n 0 = if\n      n 1 - loop 1 +\n    else\n      n\n    end\n  ;\nend-module\n')
    if_node = program.words[0].body.items[3]
    assert isinstance(if_node, IfNode)
    call = if_node.then_block.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []

def test_checker_does_not_mark_mutual_recursion_as_self_tail_call() -> None:
    program = check_source('module @app\n  : a { n:Int -- n2:Int }\n    n 1 - b\n  ;\n  : b { n:Int -- n2:Int }\n    n 1 - a\n  ;\nend-module\n')
    call_a = program.words[0].body.items[3]
    call_b = program.words[1].body.items[3]
    assert isinstance(call_a, IdentifierNode)
    assert isinstance(call_b, IdentifierNode)
    assert call_a.resolution.is_self_tail_call is False
    assert call_b.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []
    assert _marked_calls(program.words[1].body) == []

def test_checker_does_not_mark_indirect_recursion_as_self_tail_call() -> None:
    program = check_source('module @app\n  : a { n:Int -- n2:Int }\n    n 0 = if\n      n\n    else\n      n 1 - b\n    end\n  ;\n  : b { n:Int -- n2:Int }\n    n 1 - a\n  ;\nend-module\n')
    if_node = program.words[0].body.items[3]
    assert isinstance(if_node, IfNode)
    call_to_b = if_node.else_block.items[3]
    call_to_a = program.words[1].body.items[3]
    assert isinstance(call_to_b, IdentifierNode)
    assert isinstance(call_to_a, IdentifierNode)
    assert call_to_b.resolution.is_self_tail_call is False
    assert call_to_a.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []
    assert _marked_calls(program.words[1].body) == []

def test_checker_does_not_mark_self_call_inside_quotation() -> None:
    program = check_source('module @app\n  : loop { -- n:Int }\n    :[ | -- n:Int | loop ;] drop\n    0\n  ;\nend-module\n')
    quote = program.words[0].body.items[0]
    assert isinstance(quote, QuoteNode)
    call = quote.body.items[0]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []

def test_checker_marks_self_call_in_tail_case_branch() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n case\n      0 => 0\n      _ => n 1 - loop\n    end\n  ;\nend-module\n')
    case_node = program.words[0].body.items[1]
    assert isinstance(case_node, CaseNode)
    call = case_node.branches[1].body.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is True
    assert _marked_calls(program.words[0].body) == [call]

def test_checker_marks_self_call_in_guarded_tail_case_branch() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n case\n      _ when n 0 > => n 1 - loop\n      _ => n\n    end\n  ;\nend-module\n')
    case_node = program.words[0].body.items[1]
    assert isinstance(case_node, CaseNode)
    call = case_node.branches[0].body.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is True
    assert _marked_calls(program.words[0].body) == [call]

def test_checker_does_not_mark_self_call_inside_case_guard_as_tail() -> None:
    program = check_source('module @app\n  : loop { n:Int -- n2:Int }\n    n case\n      _ when n 1 - loop 0 > => n\n      _ => n\n    end\n  ;\nend-module\n')
    case_node = program.words[0].body.items[1]
    assert isinstance(case_node, CaseNode)
    guard = case_node.branches[0].guard
    assert guard is not None
    call = guard.items[3]
    assert isinstance(call, IdentifierNode)
    assert call.name == 'loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(program.words[0].body) == []

def test_checker_effect_analysis_distinguishes_same_name_words_across_modules() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    source = 'module @a\n  : run { -- n:Int }\n    1\n  ;\nend-module\nmodule @b\n  dirty : run { msg:String -- }\n    msg host.log\n  ;\nend-module'
    program = _parse_source(source)
    symbols = collect_signatures(program)
    contract = host_contract_from_words([HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])
    resolved = resolve(program, symbols, host_contract=contract)
    analysis = Checker(symbols)._analyze_effects(resolved)
    assert len(set(analysis.word_order)) == 2
    assert '@a.run' in analysis.effects
    assert '@b.run' in analysis.effects
    assert analysis.effects['@a.run'].inferred_dirty is False
    assert analysis.effects['@b.run'].inferred_dirty is True

def test_checker_rejects_pure_cross_module_call_to_dirty_same_name_word() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract_without_builtins('module @b\n  dirty : run { msg:String -- }\n    msg host.log\n  ;\nend-module\nmodule @a\n  import @b\n  : run { msg:String -- }\n    msg @b.run\n  ;\nend-module', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_does_not_mark_cross_module_same_name_tail_call_as_self() -> None:
    program = check_source_without_builtins('module @b\n  : loop { n:Int -- n2:Int }\n    n\n  ;\nend-module\nmodule @a\n  import @b\n  : loop { n:Int -- n2:Int }\n    n @b.loop\n  ;\nend-module')
    a_loop = get_module_word(program, module_name='a', word_name='loop')
    call = a_loop.body.items[1]
    assert isinstance(call, IdentifierNode)
    assert call.name == '@b.loop'
    assert call.resolution.is_self_tail_call is False
    assert _marked_calls(a_loop.body) == []

def test_checker_phase4_scc_dirty_propagation_passes_with_annotations():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : even { msg:String -- }\n    msg odd\n  ;\n  dirty : odd { msg:String -- }\n    msg host.log\n    msg even\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_rejects_pure_to_dirty_direct_call():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  : a { msg:String -- }\n    msg b\n  ;\n  dirty : b { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_module_effect_preservation():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : send { msg:String -- }\n    msg host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_subword_dirty_propagation_requires_dirty_parent():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  : outer { msg:String -- }\n    dirty : inner { msg:String -- }\n      msg host.log\n    ;\n    msg inner\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_if_branch_union_is_conservative():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  dirty : dirty-worker { msg:String -- }\n    msg host.log\n  ;\n  : main { b:Bool msg:String -- }\n    b if\n      msg dirty-worker\n    else\n      msg drop\n    end\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase4_case_branch_union_is_conservative():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  dirty : dirty-worker { msg:String -- }\n    msg host.log\n  ;\n  : main { b:Bool msg:String -- }\n    b case\n      true => msg dirty-worker\n      false => msg drop\n    end\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_accepts_pure_quote_type_from_pure_quotation_body():
    check_source('module @app\n  : make { -- q:Quote<{ | x:Int -- y:Int }> }\n    :[ | x:Int -- y:Int | x 1 + ;]\n  ;\nend-module\n')

def test_checker_phase5_accepts_dirtyquote_type_from_dirty_quotation_body():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : make { msg:String -- q:DirtyQuote<{ captured:String | x:Int -- y:Int }> }\n    msg\n    :[ captured:String | x:Int -- y:Int |\n      captured host.log\n      x\n    ;]\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_rejects_pure_frame_constructing_dirtyquote():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='pure frame cannot construct DirtyQuote'):
        check_source_with_host_contract('module @app\n  : make { msg:String -- q:DirtyQuote<{ captured:String | x:Int -- y:Int }> }\n    msg\n    :[ captured:String | x:Int -- y:Int |\n      captured host.log\n      x\n    ;]\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_accepts_dirty_frame_constructing_pure_quote():
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : make { msg:String -- q:Quote<{ | x:Int -- y:Int }> }\n    msg host.log\n    :[ | x:Int -- y:Int | x 1 + ;]\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_rejects_call_dirtyquote_in_pure_frame():
    with pytest.raises(CheckerError, match='pure frame cannot call DirtyQuote'):
        check_source('module @app\n  : run { x:Int q:DirtyQuote<{ | n:Int -- m:Int }> -- y:Int }\n    x q call\n  ;\nend-module\n')

def test_checker_phase5_accepts_call_dirtyquote_in_dirty_frame():
    check_source('module @app\n  dirty : run { x:Int q:DirtyQuote<{ | n:Int -- m:Int }> -- y:Int }\n    x q call\n  ;\nend-module\n')

def test_checker_phase5_rejects_list_map_dirtyquote_in_pure_frame():
    with pytest.raises(CheckerError, match='pure frame cannot pass DirtyQuote to list.map'):
        check_source('module @app\n  : map-it { xs:List<Int> q:DirtyQuote<{ | x:Int -- y:Int }> -- ys:List<Int> }\n    xs q list.map\n  ;\nend-module\n')

def test_checker_phase5_accepts_list_map_dirtyquote_in_dirty_frame():
    check_source('module @app\n  dirty : map-it { xs:List<Int> q:DirtyQuote<{ | x:Int -- y:Int }> -- ys:List<Int> }\n    xs q list.map\n  ;\nend-module\n')

@pytest.mark.parametrize('builtin_name', ['list.filter', 'list.fold', 'list.reduce'])
def test_checker_phase5_rejects_dirtyquote_for_other_hofs_in_pure_frame(builtin_name: str):
    if builtin_name == 'list.filter':
        source = 'module @app\n  : use-filter { xs:List<Int> q:DirtyQuote<{ | x:Int -- keep:Bool }> -- ys:List<Int> }\n    xs q list.filter\n  ;\nend-module\n'
    elif builtin_name == 'list.fold':
        source = 'module @app\n  : use-fold { xs:List<Int> init:Int q:DirtyQuote<{ | acc:Int x:Int -- out:Int }> -- out:Int }\n    xs init q list.fold\n  ;\nend-module\n'
    else:
        source = 'module @app\n  : use-reduce { xs:List<Int> q:DirtyQuote<{ | a:Int b:Int -- c:Int }> -- out:Int }\n    xs q list.reduce\n  ;\nend-module\n'
    with pytest.raises(CheckerError, match=f'pure frame cannot pass DirtyQuote to {builtin_name}'):
        check_source(source)

@pytest.mark.parametrize('builtin_name', ['list.filter', 'list.fold', 'list.reduce'])
def test_checker_phase5_accepts_dirtyquote_for_other_hofs_in_dirty_frame(builtin_name: str):
    if builtin_name == 'list.filter':
        source = 'module @app\n  dirty : use-filter { xs:List<Int> q:DirtyQuote<{ | x:Int -- keep:Bool }> -- ys:List<Int> }\n    xs q list.filter\n  ;\nend-module\n'
    elif builtin_name == 'list.fold':
        source = 'module @app\n  dirty : use-fold { xs:List<Int> init:Int q:DirtyQuote<{ | acc:Int x:Int -- out:Int }> -- out:Int }\n    xs init q list.fold\n  ;\nend-module\n'
    else:
        source = 'module @app\n  dirty : use-reduce { xs:List<Int> q:DirtyQuote<{ | a:Int b:Int -- c:Int }> -- out:Int }\n    xs q list.reduce\n  ;\nend-module\n'
    check_source(source)

@pytest.mark.parametrize(('source', 'host_words'), [('module @app\n  dirty : leaf { msg:String -- }\n    msg host.log\n  ;\n  dirty : make { msg:String -- q:DirtyQuote<{ captured:String | x:Int -- y:Int }> }\n    msg\n    :[ captured:String | x:Int -- y:Int |\n      captured leaf\n      x\n    ;]\n  ;\nend-module\n', [('host.log', '{ msg:String -- }', HostEffect.DIRTY)]), ('module @app\n  : helper { x:Int -- y:Int }\n    x 1 +\n  ;\n  : make { -- q:Quote<{ | x:Int -- y:Int }> }\n    :[ | x:Int -- y:Int | x helper ;]\n  ;\nend-module\n', [])])
def test_checker_phase5_quote_body_effect_from_called_words(source: str, host_words):
    if not host_words:
        check_source(source)
        return
    resolved_host_words = [HostWord(name=name, signature=signature_from_source(f'module @app\n  : hostsig{signature_src} ;\nend-module\n'), effect=effect) for name, signature_src, effect in host_words]
    check_source_with_host_contract(source, resolved_host_words)

def test_checker_phase5_graph_case1_unannotated_dirty_callee_in_quote_marks_quote_dirty() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='inferred dirty.*missing dirty annotation'):
        check_source_with_host_contract('module @app\n  : b { -- }\n    "x" host.log\n  ;\n  dirty : a { -- }\n    :[ | -- |\n      b\n    ;]\n    call\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_graph_case2_annotated_dirty_callee_in_quote() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : b { -- }\n    "x" host.log\n  ;\n  dirty : a { -- }\n    :[ | -- |\n      b\n    ;]\n    call\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_graph_case3_recursive_quote_cycle_without_dirty_source_stays_pure() -> None:
    check_source('module @app\n  : a { -- }\n    :[ | -- |\n      a\n    ;]\n    drop\n  ;\nend-module\n')

def test_checker_phase5_graph_case4_pure_words_with_dirty_quote_path_fail_missing_dirty() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError, match='pure frame cannot construct DirtyQuote'):
        check_source_with_host_contract('module @app\n  : a { -- }\n    :[ | -- |\n      b\n    ;]\n    call\n  ;\n  : b { -- }\n    "x" host.log\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])

def test_checker_phase5_graph_case5_nested_quotes_propagate_dirty() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    check_source_with_host_contract('module @app\n  dirty : b { -- }\n    "x" host.log\n  ;\n  dirty : a { -- }\n    :[ | -- |\n      :[ | -- |\n        b\n      ;]\n      call\n    ;]\n    call\n  ;\nend-module\n', [HostWord(name='host.log', signature=host_signature, effect=HostEffect.DIRTY)])


def test_checker_if_condition_error_exposes_structured_diagnostic() -> None:
    source = (
        "module @app\n"
        "  : bad { x:Int -- y:Int }\n"
        "    x if\n"
        "      1\n"
        "    else\n"
        "      2\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(CheckerError) as exc_info:
        check_source(source)
    error = exc_info.value
    program = _parse_source(source)
    word = get_module_word(program, module_name="app", word_name="bad")
    if_node = next(item for item in word.body.items if isinstance(item, IfNode))
    diagnostic_span = error.diagnostic.span
    assert diagnostic_span is not None
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_IF_CONDITION_NOT_BOOL"
    assert error.message == "if condition must be Bool"
    assert diagnostic_span == if_node.span
    assert diagnostic_span.source.path == MEMORY_SOURCE_PATH
    assert diagnostic_span.source.path != SYNTHETIC_SOURCE_PATH
    assert error.line == diagnostic_span.line
    assert error.column == diagnostic_span.column


def test_checker_list_append_value_mismatch_exposes_structured_diagnostic() -> None:
    source = (
        "module @app\n"
        "  : bad { -- xs:List<Int> }\n"
        "    [1, 2] \"oops\" list.append\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(CheckerError) as exc_info:
        check_source(source)
    error = exc_info.value
    program = _parse_source(source)
    word = get_module_word(program, module_name="app", word_name="bad")
    list_append = _find_identifier(word.body, "list.append")
    diagnostic_span = error.diagnostic.span
    assert diagnostic_span is not None
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_LIST_APPEND_VALUE_TYPE_MISMATCH"
    assert error.message == "list.append value type does not match list element type"
    assert diagnostic_span == list_append.span
    assert diagnostic_span.source.path == MEMORY_SOURCE_PATH
    assert diagnostic_span.source.path != SYNTHETIC_SOURCE_PATH
    assert error.line == diagnostic_span.line
    assert error.column == diagnostic_span.column


def test_checker_case_pattern_mismatch_exposes_structured_diagnostic() -> None:
    with pytest.raises(CheckerError) as exc_info:
        check_source(
            "module @app\n"
            "  : bad { b:Bool -- n:Int }\n"
            "    b case\n"
            "      1 => 1\n"
            "      _ => 0\n"
            "    end\n"
            "  ;\n"
            "end-module\n"
        )
    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_CASE_PATTERN_TYPE_MISMATCH"
    assert error.message == "case pattern does not match scrutinee type"


def test_checker_case_guard_dirty_call_exposes_structured_diagnostic() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    source = (
        "module @app\n"
        "  dirty : use-guard { r:Result<Int,MapError> -- n:Int }\n"
        "    r case\n"
        "      Ok(v) when \"x\" host.log true => v\n"
        "      _ => 0\n"
        "    end\n"
        "  ;\n"
        "end-module\n"
    )
    with pytest.raises(CheckerError) as exc_info:
        check_source_with_host_contract(
            source,
            [HostWord(name="host.log", signature=host_signature, effect=HostEffect.DIRTY)],
        )
    error = exc_info.value
    program = _parse_source(source)
    word = get_module_word(program, module_name="app", word_name="use-guard")
    host_call = _find_identifier(word.body, "host.log")
    diagnostic_span = error.diagnostic.span
    assert diagnostic_span is not None
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_CASE_GUARD_CALLS_DIRTY_CODE"
    assert error.message == "case guard cannot call dirty code"
    assert diagnostic_span == host_call.span
    assert diagnostic_span.source.path == MEMORY_SOURCE_PATH
    assert diagnostic_span.source.path != SYNTHETIC_SOURCE_PATH
    assert error.line == diagnostic_span.line
    assert error.column == diagnostic_span.column


def test_checker_dirty_annotation_missing_exposes_structured_diagnostic() -> None:
    host_signature = signature_from_source('module @app\n  : hostsig { msg:String -- } ;\nend-module\n')
    with pytest.raises(CheckerError) as exc_info:
        check_source_with_host_contract(
            "module @app\n"
            "  : write-log { msg:String -- }\n"
            "    msg host.log\n"
            "  ;\n"
            "end-module\n",
            [HostWord(name="host.log", signature=host_signature, effect=HostEffect.DIRTY)],
        )
    error = exc_info.value
    assert error.diagnostic.phase is DiagnosticPhase.CHECKER
    assert error.diagnostic.code == "CHECKER_DIRTY_ANNOTATION_MISSING"
    assert "missing dirty annotation" in error.message
