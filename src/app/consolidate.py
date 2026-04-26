import collections.abc
import dataclasses
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from app.database import iter_all_files, iter_hashed_files_with_id
from app.cleanup import DuplicateFile

"""Interactive duplicate folder cleanup for raw-deduplicator_v2.

Analyzes duplicate files by folder, provides an interactive TUI for
selecting which folders' duplicates to remove, and executes deletion
with last-copy safety protection.
"""

# _GB: int = 1024**3
# _MB: int = 1024**2
# _KB: int = 1024

"""
# Plan:

## Get inputs

1. Destination root
2. Dest dupes
3. Source files (all files not under dest)
4. dupes where:
  - versions exist in source
  - no versions exist in dest

### Copy list

* all source_files
* exclude if a version exists in destination
* if dupe, select alpha first for copy
* if not dupe, assume should be copied

"""


# def build_duplicate_groups(conn: sqlite3.Connection) -> dict[str, list[DuplicateFile]]:
#     """Build duplicate groups from hashed files in the database.
#
#     Groups files by (file_size, md5_hash, sha256_hash). Only groups with
#     2 or more files are returned. Prints progress while scanning.
#
#     Args:
#         conn: An open SQLite connection to the files database.
#
#     Returns:
#         A dict mapping group keys to lists of DuplicateFile objects.
#         Only groups with 2+ files are included.
#     """
#     total: int = count_hashed_files(conn)
#     index: dict[str, list[DuplicateFile]] = defaultdict(list)
#
#     cursor: sqlite3.Cursor = iter_hashed_files_with_id(conn)
#     for current, row in enumerate(cursor, start=1):
#         file_id: int = row[0]
#         file_size: int = row[1]
#         md5_hash: str = row[2]
#         sha256_hash: str = row[3]
#         rel_path: str = row[4]
#
#         key: str = f"{file_size}_{md5_hash}_{sha256_hash}"
#         folder: str = str(PurePosixPath(rel_path).parent)
#
#         index[key].append(
#             DuplicateFile(
#                 file_id=file_id,
#                 rel_path=rel_path,
#                 file_size=file_size,
#                 group_key=key,
#                 folder=folder,
#             )
#         )
#
#         if current % 10000 == 0 or current == total:
#             print(f"  [{current}/{total}] Grouping files by hash ...", end="\r")
#
#     if total > 0:
#         print()
#
#     duplicate_groups: dict[str, list[DuplicateFile]] = {k: v for k, v in index.items() if len(v) > 1}
#     duplicate_count: int = sum(len(v) for v in duplicate_groups.values())
#     print(f"  {duplicate_count} duplicate files in {len(duplicate_groups)} groups")
#
#     return duplicate_groups


def get_non_dupes_to_copy():

    return []


#todo: use something like this to decide what needs NOT be copied
#all other scanned files in Onedrive/google will need to be copied to proton
def get_dupes_not_in_dest(
    duplicate_groups: dict[str, list[DuplicateFile]],
    destination_root: str,
) -> list[str]:
    """Determine which duplicate files to copy from source based on presence in destination.

    For each duplicate group, files in source folders are marked for
    copy if not present in destination. If multiple copies exist in source folders, the
    alphabetically first copy is picked.

    Args:
        duplicate_groups: Dict mapping group keys to lists of DuplicateFile.
        destination_root: String denoting root of destination path.

    Returns:
        A list of duplicate files to copy to destination.
    """
    # copies: list[FileCopy] = [] #TODO - ?
    copies: list[str] = []

    #triage files in sources vs destination
    for files in duplicate_groups.values():
        #todo: path check is probs wrong, use helper?
        in_destination = list[DuplicateFile] = [f for f in files if f.folder.startswith(str(destination_root))]
        in_source =  list[DuplicateFile] = [f for f in files if not f.folder.startswith(str(destination_root))]
        if size(in_destination) == 0 and in_source:
            sorted_files: list[DuplicateFile] = sorted(in_selected, key=lambda f: f.rel_path)
            copies.append(sorted_files[0])

    # probably handle plan info - file count, total bytes - in caller
    return copies


def build_copy_groups(
    conn: sqlite3.Connection,
    source_files: list[str],
) -> dict[str, list[DuplicateFile]]:
    """Build duplicate groups from hashed files in the database.

    Groups files by (file_size, md5_hash, sha256_hash). Only groups with
    2 or more files are returned. Prints progress while scanning.

    Args:
        conn: An open SQLite connection to the files database.

    Returns:
        A dict mapping group keys to lists of DuplicateFile objects.
        Only groups with 2+ files are included.
    """

    # total: int = count_hashed_files(conn)
    index: dict[str, list[DuplicateFile]] = defaultdict(list)

    cursor: sqlite3.Cursor = iter_hashed_files_with_id(conn)
    for current, row in enumerate(cursor, start=1):
        file_id: int = row[0]
        file_size: int = row[1]
        md5_hash: str = row[2]
        sha256_hash: str = row[3]
        rel_path: str = row[4]

        key: str = f"{file_size}_{md5_hash}_{sha256_hash}"
        folder: str = str(PurePosixPath(rel_path).parent)

        index[key].append(
            DuplicateFile(
                file_id=file_id,
                rel_path=rel_path,
                file_size=file_size,
                group_key=key,
                folder=folder,
            )
        )

        if current % 10000 == 0 or current == total:
            print(f"  [{current}/{total}] Grouping files by hash ...", end="\r")

    if total > 0:
        print()

    duplicate_groups: dict[str, list[DuplicateFile]] = {k: v for k, v in index.items() if len(v) > 1}
    duplicate_count: int = sum(len(v) for v in duplicate_groups.values())
    print(f"  {duplicate_count} duplicate files in {len(duplicate_groups)} groups")

    return duplicate_groups


def plan_copies(
    scanned_files: list[str],
    duplicate_groups: dict[str, list[DuplicateFile]],
    destination_root: str,
):
#) -> CopyPlan:
    #get list of source files - all not in destination
    # eg     # files_to_copy = {
    #     all scanned_files NOT in destination (full scan)
    #     AND not in "in_destination" list
    # }

    source_files = [f for f in scanned_files if not f.startswith(str(destination_root))]

    # non_dupes_to_copy = {
    #     all source_files NOT in duplicate_groups
    #     AND not in destination (use helper)
    # }

    dupes_to_copy = get_dupes_not_in_dest(
        duplicate_groups,
        destination_root,
    )

    files_to_copy = [] #union of dupes_to_copy + non_dupes_to_copy

    return files_to_copy


def run_consolidation(
    conn: sqlite3.Connection,
    base_path: Path,
    destination_root: Path,
    force: bool,
) -> None:

    cursor: sqlite3.Cursor = iter_all_files(conn)
    scanned_files = [f.rel_path for f in enumerate(cursor, start=1)]

    source_files = [f for f in scanned_files if not f.startswith(str(destination_root))]
    # duplicate_groups = build_duplicate_groups(conn)
    duplicate_groups = build_copy_groups(conn, source_files)

    plan_copies(
        scanned_files,
        duplicate_groups,
        destination_root,
    )


