"""Single source of truth for the package version.

Imported by ``drought_forecast_eval/__init__.py`` **and** by submodules that
need the version string (e.g. ``report/builder.py``) without triggering a
circular import through the package root.
"""

__version__: str = "0.1.0"
