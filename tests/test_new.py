"""Tests for the scanner module."""

import pytest

from app.config import ScannerConfig
import app.scanner as sc


def _make_config(scan_path, **overrides):
    defaults = {
        "paths": [str(scan_path)],
        "extensions": [".*"],
        "case_sensitive": False,
        "recursive": True,
        "skip_dirs": ["skipped"],
        "skip_files": [".lock"],
        "database": "unused.db",
        "consolidation_destination": "",
    }
    defaults.update(overrides)
    return ScannerConfig(**defaults)


class TestCrawlDirs:
    def test_crawls_dirs(self, tmp_path):
        #sub directory to avoid picking up db files
        subdir = (tmp_path / "files")
        subdir.mkdir()
        subdir2 = (subdir / "skipped")
        subdir2.mkdir()
        subdir3 = (subdir2 / "child")
        subdir3.mkdir()

        (subdir2 / "readme.txt").write_text("data")
        (subdir3 / "process.log").write_text("data")
        (subdir / ".lock").write_text("data")
        (subdir / "photo.jpg").write_text("data")
        (subdir / "image.png").write_text("data")

        config = _make_config(subdir)
        print("[DEBUG]:", config.paths)
        sc.test_crawl(
            root=subdir,
            extensions=config.extensions,
            case_sensitive=config.case_sensitive,
            recursive=config.recursive,
            skip_dirs=config.skip_dirs,
            skip_files=config.skip_files,
        )

        assert 1 == 0
