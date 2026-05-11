"""gsigmad -- Science governance CLI."""
from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("gsigmad")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"
