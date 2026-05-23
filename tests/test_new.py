"""Tests for the scanner module."""

import pytest

from app.config import ScannerConfig
from app.database import count_total_files, count_excluded_files, count_file_conditional, count_total_files_all, open_database
from app.scanner import scan_files


## TODO: test FileResult -> FileRecord


@pytest.fixture()
def db_conn(tmp_path):
    db_path = tmp_path / "test.db"
    conn = open_database(db_path)
    yield conn
    conn.close()


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


def _run(conn, query):
    for row in conn.execute(query).fetchall():
        print(row)


class TestScanFilesAll:
    def test_finds_files_all(self, tmp_path, db_conn):
        #sub directory to avoid picking up db files
        subdir = (tmp_path / "files")
        subdir.mkdir()
        subdir2 = (subdir / "skipped")
        subdir2.mkdir()

        (subdir2 / "readme.txt").write_text("data")
        (subdir / ".lock").write_text("data")
        (subdir / "photo.jpg").write_text("data")
        (subdir / "image.png").write_text("data")

        config = _make_config(subdir)
        scan_files(config=config, conn=db_conn)

        q = "PRAGMA table_info('files')"
        print("[DEBUG]:", q)
        # _run(db_conn, q)
        for r in db_conn.execute(q).fetchall():
            print("[DEBUG]:", r)

        assert count_total_files_all(db_conn) == 4
        assert count_file_conditional(db_conn, condition="is_included is null") == 0

        print("[DEBUG]: all")


class TestScanFileInclusion:
    def runinc(self, conn, query):
        for row in conn.execute(query).fetchall():
            print('Included:', ', '.join([str(r) for r in row]))

    def test_finds_files_included(self, tmp_path, db_conn):
        #sub directory to avoid picking up db files
        subdir = (tmp_path / "files")
        subdir.mkdir()
        subdir2 = (subdir / "skipped")
        subdir2.mkdir()

        (subdir2 / "readme.txt").write_text("data")
        (subdir / ".lock").write_text("data")
        (subdir / "photo.jpg").write_text("data")
        (subdir / "image.png").write_text("data")

        config = _make_config(subdir)
        scan_files(config=config, conn=db_conn)

        q = 'SELECT is_included, count(*), 1.0*sum(file_size)/1024/1024/1024 FROM files GROUP BY is_included'
        self.runinc(db_conn, q)

        print("[DEBUG]: included", str(count_total_files(db_conn)))

        assert count_total_files(db_conn) == 2


class TestScanFileExclusion:

    def test_finds_files_excluded(self, tmp_path, db_conn):
        #sub directory to avoid picking up db files
        subdir = (tmp_path / "files")
        subdir.mkdir()
        subdir2 = (subdir / "skipped")
        subdir2.mkdir()

        (subdir2 / "readme.txt").write_text("data")
        (subdir / ".lock").write_text("data")
        (subdir / "photo.jpg").write_text("data")
        (subdir / "image.png").write_text("data")

        config = _make_config(subdir)
        scan_files(config=config, conn=db_conn)

        print("[DEBUG]: excluded", str(count_excluded_files(db_conn)))

        assert count_excluded_files(db_conn) == 2

