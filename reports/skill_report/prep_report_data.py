"""Pack the scoring outputs into the report page and copy the meteogram shards.

Run from the repo root after categorical_skill.py and numeric_skill.py:
    poetry run python reports/skill_report/prep_report_data.py reports/skill_report/out

Writes <out_dir>/site/index.html (template + inlined data) and <out_dir>/site/mg/*.json.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import MultiPolygon

HERE = Path(__file__).parent
SHAPEFILE = "shapefiles/BAFU_Grossregionen_v3.shp"


def r(x, n=3):
    return None if x is None else round(x, n)


def categorical(cat: dict) -> dict:
    out = {}
    for per, p in cat["periods"].items():
        po = {"n_weeks": p["n_weeks"], "idx": {}}
        for v, leads in p["indices"].items():
            rows = []
            for lw in "0123":
                e = leads[lw]
                row = {
                    "tab": e["table"],
                    "chg": {k: r(x) for k, x in e["change"].items()},
                    "diff": {k.split(".", 1)[1]: [r(c[0]), r(c[1])] for k, c in e["ci90"].items()},
                }
                for s in ("fcst", "pers"):
                    row[s] = {k: r(x) for k, x in e[s]["multi"].items()}
                    row[s]["bin"] = {
                        k: {m: r(x) for m, x in b.items()} for k, b in e[s]["binary"].items()
                    }
                rows.append(row)
            po["idx"][v] = rows
        out[per] = po
    return out


def numeric(num: dict) -> dict:
    keep = (
        "mae_f", "mae_p", "mae_c", "maess_p", "maess_c", "qss_c", "bss", "auc", "event_rate",
        "bias", "rbias", "cov80_f", "width_ratio",
    )  # fmt: skip
    out = {}
    for per, p in num["periods"].items():
        out[per] = {
            v: [
                {k: r(e[k]) for k in keep}
                | {
                    "bins_f": [r(x) for x in e["bins_f"]],
                    "bins_c": [r(x) for x in e["bins_c"]],
                    "ci": {k: [r(c[0]), r(c[1])] for k, c in e["ci90"].items()},
                }
                for e in leads
            ]
            for v, leads in p["vars"].items()
        }
    return out


def region_map(regional: dict) -> dict:
    g = gpd.read_file(SHAPEFILE)
    g["geometry"] = g.geometry.simplify(0.004, preserve_topology=True)
    lat0 = np.deg2rad(46.8)
    minx, miny, maxx, maxy = g.total_bounds
    w = 600.0
    sx = w / ((maxx - minx) * np.cos(lat0))

    def ring(coords):
        pts = [f"{(x - minx) * np.cos(lat0) * sx:.1f},{(maxy - y) * sx:.1f}" for x, y in coords]
        return "M" + "L".join(pts) + "Z"

    regions = []
    for _, row in g.iterrows():
        polys = row.geometry.geoms if isinstance(row.geometry, MultiPolygon) else [row.geometry]
        rid = str(int(row.REGION_NR))
        vals = []
        for lw in "0123":
            e = regional["cdi"][lw].get(rid)
            vals.append({"f": r(e["fcst"]), "p": r(e["pers"])} if e else None)
        regions.append(
            {"id": int(rid), "name": row.Name, "d": "".join(ring(p.exterior.coords) for p in polys), "v": vals}
        )
    return {"w": w, "h": round(float((maxy - miny) * sx), 1), "regions": regions}


def main() -> None:
    out_dir = Path(sys.argv[1])
    cat = json.loads((out_dir / "categorical_skill.json").read_text())
    num = json.loads((out_dir / "numeric_skill.json").read_text())
    data = {
        "cat": categorical(cat),
        "num": numeric(num),
        "map": region_map(cat["regional"]),
        "timeline": cat["timeline"],
        "regions": {},
    }
    g = gpd.read_file(SHAPEFILE)
    data["regions"] = {int(a): b for a, b in zip(g.REGION_NR, g.Name)}
    s = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    assert "</" not in s

    site = out_dir / "site"
    (site / "mg").mkdir(parents=True, exist_ok=True)
    html = (HERE / "report_template.html").read_text().replace("__DATA__", s)
    (site / "index.html").write_text(html)
    for f in (out_dir / "mg").glob("*.json"):
        shutil.copy(f, site / "mg" / f.name)
    print(f"index.html {len(html) / 1e3:.0f} kB")


if __name__ == "__main__":
    main()
