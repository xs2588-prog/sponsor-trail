"""Registry of data sources. Each one is queried by its own Researcher.

To add your source: fill in sources/<name>.py (copy sources/example.py) and
list it in ALL_SOURCES. The Lead only sees a source once available() is True,
i.e. its cleaned data files exist.
"""

import os

from sources import example, lca, perm, uscis
from sources.base import SqlSource

ALL_SOURCES: list[SqlSource] = [lca.SOURCE, uscis.SOURCE, perm.SOURCE, example.SOURCE]


def active_sources() -> dict[str, SqlSource]:
    """name -> source, for every source whose data is loaded."""
    show_example = os.environ.get("SPONSOR_EXAMPLE_SOURCE", "1") != "0"
    return {
        s.name: s for s in ALL_SOURCES
        if s.available() and (s.name != "example" or show_example)
    }
