"""Layer 6 composite graph access and repository navigation."""

from typing import TYPE_CHECKING

from bridger.contracts.navigation import (
    CompositeEntityView,
    FileOverview,
    GraphCommunityView,
    GraphDirection,
    GraphTraversalView,
    RepositorySearchHit,
    RepositorySearchKind,
    SourceContentMatch,
)
from bridger.navigation.brain import BrainNavigator
from bridger.navigation.bridger import BridgerNavigator
from bridger.navigation.navigator import RepositoryNavigator
from bridger.navigation.tools import NAVIGATION_TOOL_IDS, build_navigation_tools

if TYPE_CHECKING:
    from bridger.navigation.bootstrap import load_bridger_navigator

__all__ = [
    "CompositeEntityView",
    "BrainNavigator",
    "BridgerNavigator",
    "FileOverview",
    "GraphCommunityView",
    "GraphDirection",
    "GraphTraversalView",
    "load_bridger_navigator",
    "NAVIGATION_TOOL_IDS",
    "RepositoryNavigator",
    "RepositorySearchHit",
    "RepositorySearchKind",
    "SourceContentMatch",
    "build_navigation_tools",
]


def __getattr__(name: str) -> object:
    """Load the application bootstrap without creating package import cycles."""
    if name == "load_bridger_navigator":
        from bridger.navigation.bootstrap import load_bridger_navigator

        return load_bridger_navigator
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
