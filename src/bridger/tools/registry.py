from agents import FunctionTool

from bridger.tools.definitions import (
    get_symbol,
    grep_contents,
    inspect_manifest,
    list_ci_files,
    list_config_files,
    list_docs_files,
    list_files,
    list_instruction_files,
    list_symbols,
    list_tree,
    read_file_excerpt,
    read_symbol_excerpt,
    search_paths,
    search_symbols,
    validate_paths,
)


def get_discovery_tools() -> list[FunctionTool]:
    return [
        list_files,
        list_tree,
        search_paths,
        grep_contents,
        read_file_excerpt,
        inspect_manifest,
        list_config_files,
        list_docs_files,
        list_instruction_files,
        list_ci_files,
        search_symbols,
        list_symbols,
        get_symbol,
        read_symbol_excerpt,
        validate_paths,
    ]
