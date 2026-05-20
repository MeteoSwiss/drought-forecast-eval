# Contributing to drought-forecast-eval

## Development setup

```bash
git clone https://github.com/MeteoSwiss/drought-forecast-eval.git
cd drought-forecast-eval
poetry install --with dev,report
```

## Running tests

```bash
poetry run pytest                          # all tests with coverage
poetry run pytest tests/test_scoring.py    # single module
poetry run pytest -k "test_mae"            # by name pattern
poetry run pytest --no-header -rN -q       # quiet mode
```

Fixture ZIPs are auto-generated on first run via `tests/fixtures/make_fixtures.py`.
To regenerate them manually:

```bash
poetry run python tests/fixtures/make_fixtures.py
```

## Code style

This project uses `ruff` for linting and formatting:

```bash
poetry run ruff check .
poetry run ruff format .
```

## Adding a new metric

1. Implement the function in `drought_forecast_eval/scoring/skill.py`
   (or a new module) with signature `fn(fcst, obs, **kwargs) -> xr.DataArray`.
2. Register it in `drought_forecast_eval/scoring/registry.py` (or call
   `register_score()` at import time).
3. If it needs quantile inputs, add it to `QUANTILE_METRICS` in `registry.py`
   and handle it in `dispatcher._compute_quantile_score()`.
4. Add a test in `tests/test_scoring.py`.

## Adding a new variable

1. Add an entry to `VARIABLE_MAP` in `drought_forecast_eval/scoring/variable_map.py`.
2. Add the corresponding columns to `FORECAST_SCHEMA` / `OBSERVATION_SCHEMA` in
   `drought_forecast_eval/io/schema.py`.
3. Add a test row to `tests/fixtures/make_fixtures.py` and regenerate fixtures.

## Branch / MR workflow

- Branch from `main`; branch name: `feat/short-description` or `fix/issue-id`
- One MR per feature / fix
- All tests must pass; coverage should not decrease
- Squash merge preferred for a clean history
