from agents import FunctionTool

from bridger.tools.definitions import (
    inspect_manifest,
    list_files,
    list_symbols,
    read_symbol_excerpt,
    search_symbols,
    validate_paths,
)
from bridger.tools.definitions.exploration import (
    get_file_overview,
    get_inspection_status,
    inspect_repo_discovery,
    read_around_match,
    read_file_ranges,
    search_with_context,
)


def get_discovery_tools() -> list[FunctionTool]:
    return [
        inspect_repo_discovery,
        inspect_manifest,
        list_files,
        get_file_overview,
        list_symbols,
        search_symbols,
        read_symbol_excerpt,
        search_with_context,
        read_file_ranges,
        read_around_match,
        get_inspection_status,
        validate_paths,
    ]
