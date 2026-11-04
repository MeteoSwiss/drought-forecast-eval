# Prototypes

Experiments built on the verification data in this repository. They are not
part of the `drought_forecast_eval` package.

| Folder | What it is |
|--------|------------|
| [`drought_platform/`](drought_platform/README.md) | Local copy of the national drought platform's landing and region pages. It has a selectable forecast issue date, a new evaporation row, and a combined precipitation/evaporation view. |

Quick start, from the repository root:

```bash
python3 -m http.server -d prototypes/drought_platform/site 8000
# open http://localhost:8000
```

See [`drought_platform/README.md`](drought_platform/README.md) to rebuild the data.
