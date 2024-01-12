# type: ignore[attr-defined]
"""
`cotravel` is a Python cli/package created with https://github.com/TezRomacH/python-package-template
"""

from . import _types, config, load_tracks, pmap, quantize, synchronous, utils

try:
    from importlib.metadata import version, PackageNotFoundError
    try:
        __version__ = version(__name__)
    except PackageNotFoundError:  # pragma: no cover
        __version__ = "unknown"
except ImportError:  # pragma: no cover
    try:
        from importlib_metadata import version, PackageNotFoundError
        try:
            __version__ = version(__name__)
        except PackageNotFoundError:  # pragma: no cover
            __version__ = "unknown"
    except ImportError:
        __version__ = "unknown"


