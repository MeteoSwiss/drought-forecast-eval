"""Tests for io.archive: filename parsing and scan_archive()."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from drought_forecast_eval.io.archive import _parse_frt_from_filename, scan_archive

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class TestParseFrtFromFilename:
    def test_valid_filename(self):
        p = Path("trockenheitsdaten-numerisch_current.csv.202507042100.zip")
        result = _parse_frt_from_filename(p)
        assert result == datetime(2025, 7, 4)

    def test_another_valid_filename(self):
        p = Path("trockenheitsdaten-numerisch_current.csv.202611282100.zip")
        result = _parse_frt_from_filename(p)
        assert result == datetime(2026, 11, 28)

    def test_unrecognised_filename_returns_none(self):
        p = Path("some_other_file.csv")
        assert _parse_frt_from_filename(p) is None

    def test_missing_time_block_returns_none(self):
        p = Path("trockenheitsdaten-numerisch_current.csv.20250704.zip")
        # Only 8 digits, no 4-digit time suffix → shouldn't match YYYYMMDDHHII
        assert _parse_frt_from_filename(p) is None


class TestScanArchive:
    def test_returns_sorted_list(self):
        entries = scan_archive(FIXTURE_DIR)
        dates = [e[0] for e in entries]
        assert dates == sorted(dates), "Entries should be sorted by date"

    def test_returns_path_objects(self):
        entries = scan_archive(FIXTURE_DIR)
        assert all(isinstance(p, Path) for _, p in entries)

    def test_date_range_filter(self):
        entries = scan_archive(FIXTURE_DIR, date_range=("2026-03-24", "2026-03-24"))
        assert len(entries) >= 1
        for dt, _ in entries:
            assert dt.date().isoformat() == "2026-03-24"

    def test_date_range_excludes_outside(self):
        entries = scan_archive(FIXTURE_DIR, date_range=("2099-01-01", "2099-12-31"))
        assert len(entries) == 0

    def test_nonexistent_dir_raises(self):
        with pytest.raises(FileNotFoundError):
            scan_archive("/nonexistent/path/that/does/not/exist")

    def test_deduplicates_same_date(self, tmp_path):
        """If two ZIPs share the same date, only the last (lexicographically) is kept."""
        import zipfile

        for suffix in ["2100", "2200"]:
            name = f"trockenheitsdaten-numerisch_current.csv.202507012{suffix[1:]}.zip"
            with zipfile.ZipFile(tmp_path / name, "w") as zf:
                zf.writestr("dummy.txt", "x")
        entries = scan_archive(tmp_path)
        dates = [e[0] for e in entries]
        assert len(dates) == len(set(dates)), "Duplicate dates should be deduplicated"
