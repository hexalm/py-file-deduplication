"""File scanner for raw-deduplicator_v2.

Crawls configured directories, discovers files matching configured
extensions, and inserts them into the SQLite database.
"""

import os
import sqlite3
import sys
import dataclasses

from collections.abc import Iterator
from pathlib import Path

from app.config import ScannerConfig
from app.database import count_total_files, insert_file, insert_file_record, FileRecord, count_total_files_all


@dataclasses.dataclass(frozen=True)
class FileResult:
    path: Path
    file_name: str
    rel_path: str
    extension: str
    file_size: int | None
    is_included: bool
    is_found: bool | None


def convert_to_record(
    file_result: FileResult,
    file_size: int = None,
    extension: str = None,
    error_message: str = None,
) -> FileRecord:

    size = file_size if file_size else file_result.file_size
    ext = extension if file_size else file_result.extension
    return FileRecord(
        **{k: v for k, v in file_result.__dict__.items() if k not in ['extension', 'file_size', 'is_error', 'error_message']},
        file_size=size,
        extension=ext,
        is_error=error_message is not None,
        error_message=error_message,
    )


def scan_files(config: ScannerConfig, conn: sqlite3.Connection) -> None:
    """Scan configured directories and insert discovered files into the database.

    For each configured path, crawls the directory tree (respecting
    skip_dirs, extensions, case_sensitive, and recursive settings)
    and inserts each discovered file into the database. Files already
    in the database (by rel_path) are silently skipped.

    Args:
        config: The validated scanner configuration.
        conn: An open SQLite connection to the files database.
    """
    total_included: int = 0
    total_excluded: int = 0
    total_inserted: int = 0
    total_skipped: int = 0
    total_errors: int = 0

    for scan_path_str in config.paths:
        scan_root: Path = Path(scan_path_str).resolve()

        if not scan_root.exists():
            print(f"WARNING: Path does not exist, skipping: {scan_root}")
            total_errors = total_errors + 1
            continue

        if not scan_root.is_dir():
            print(f"WARNING: Path is not a directory, skipping: {scan_root}")
            total_errors = total_errors + 1
            continue

        print(f"Scanning: {scan_root}")

        included: int = 0
        excluded: int = 0

        inserted: int = 0
        skipped: int = 0
        current_dir: str = ""

        crawl = _crawl_directory(
            root=scan_root,
            extensions=config.extensions,
            case_sensitive=config.case_sensitive,
            recursive=config.recursive,
            skip_dirs=config.skip_dirs,
            skip_files=config.skip_files,
        )

        for file_result in crawl:

            if file_result.is_included:
                included += 1
            elif not file_result.is_included:
                excluded += 1
            else:
                raise("FileResult.is_included error!")

            error_message: str = None
            file_path: str = file_result.path
            parent_rel: str = str(file_path.parent.relative_to(scan_root))
            if parent_rel != current_dir:
                current_dir = parent_rel
                found: int = inserted + skipped
                display_dir: str = current_dir if current_dir != "." else str(scan_root)
                print(f"[{found} files found] Scanning ... {display_dir}")
                sys.stdout.flush()

            extension: str = file_path.suffix
            if not config.case_sensitive:
                extension = extension.lower()

            #TODO: switch for not stat on skipped files?
            try:
                file_size: int = file_path.stat().st_size
            except OSError as err:
                error_message = str(err)
                print(f"  WARNING: Could not stat {file_path}: {err}")
                total_errors = total_errors + 1

            rec: FileRecord = convert_to_record(
                file_result,
                file_size=file_size,
                extension=extension,
                error_message=error_message,
            )

            was_inserted: bool = insert_file_record(
                conn=conn,
                file_record=rec
            )

            if was_inserted:
                inserted = inserted + 1
            else:
                skipped = skipped + 1

        conn.commit()
        total_inserted = total_inserted + inserted
        total_skipped = total_skipped + skipped
        print(f"  Inserted: {inserted}, Already in DB: {skipped}")

        total_included = total_included + included
        total_excluded = total_excluded + excluded
        print(f"  Included: {included}, Not included: {excluded}")

    total_in_db: int = count_total_files_all(conn)

    print("\nScan complete.")
    print(f"  New files added: {total_inserted}")
    print(f"  Already in DB: {total_skipped}")
    print(f"  Errors: {total_errors}")
    print(f"  Total files in database: {total_in_db}")


def _crawl_directory(
    root: Path,
    extensions: list[str],
    case_sensitive: bool,
    recursive: bool,
    skip_dirs: list[str],
    skip_files: list[str],
) -> Iterator[FileResult]:
    """Crawl a directory tree for files matching given extensions.

    Does NOT follow symlinks.
    Skips directories whose names appear in the skip_dirs list.
    Skips files whose names appear in the skip_files list.

    Args:
        root: The resolved root directory to crawl.
        extensions: List of file extensions with dots (e.g., [".jpg"]).
        case_sensitive: Whether extension matching is case sensitive.
        recursive: Whether to descend into subdirectories.
        skip_dirs: List of directory names to skip.

    Yields:
        Absolute Path objects for each matching file.
    """
    skip_set: set[str] = set(skip_dirs)
    ext_set: set[str] = set()
    ext_wildcard = False

    if len(extensions) == 1 and extensions[0] in [".*", "*"]:
        ext_wildcard = True
    elif case_sensitive:
        ext_set = set(extensions)
    else:
        ext_set = {e.lower() for e in extensions}

    for dirpath, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirnames[:] = [d for d in dirnames]
        for filename in filenames:
            # print(f"======================")
            # print(f"[DEBUG] {filename}")
            dir_name = Path(dirpath).name
            # print(f"[DEBUG] {dir_name}")
            is_included = False if dir_name in skip_set else True
            full_path = Path(dirpath) / filename
            file_name = filename
            file_ext: str = os.path.splitext(file_name)[1]
            if not case_sensitive:
                file_name = file_name.lower()
                file_ext = file_ext.lower()

            if ext_wildcard and is_included:
                # print(f"[DEBUG] Wildcard")
                is_included = True
            else:
                # print(f"[DEBUG] Wildcard == False")
                if not case_sensitive:
                    # print(f"[DEBUG] not case sensitive")
                    file_ext = file_ext.lower()
                if file_ext not in ext_set:
                    # print(f"[DEBUG] file ext not in ext set")
                    is_included = False

            # if exclude_hidden and filename.startswith("."):
            #     is_included = False
            # elif ...

            if file_name in skip_files:
                # print(f"[DEBUG] file in skip_files: {file_name}")
                is_included = False

            yield FileResult(
                path=full_path,
                file_name=filename,
                rel_path=str(full_path.relative_to(root)),
                extension=file_ext,
                file_size=None,
                is_included=is_included,
                is_found=False,
            )

        if not recursive:
            dirnames.clear()
