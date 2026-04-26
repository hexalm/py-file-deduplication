import collections.abc
import dataclasses
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from app.database import iter_all_files, iter_hashed_files_with_id
from app.cleanup import DuplicateFile, build_duplicate_groups

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


def get_duplicate_groups_by_status(
    destination_root: Path,
    duplicate_groups: dict[str, list[DuplicateFile]],
) -> (dict[str, list[DuplicateFile]], dict[str, list[DuplicateFile]]):

    duplicates_not_in_destination: dict[str, list[DuplicateFile]] = dict()
    duplicates_in_destination: dict[str, list[DuplicateFile]] = dict()

    for group, files in duplicate_groups.items():
        if [f for f in files if f.folder.startswith(str(destination_root))]:
            duplicates_in_destination.update({group: files})
        else:
            duplicates_not_in_destination.update({group: files})

    return (duplicates_in_destination, duplicates_not_in_destination)


def get_files_to_copy(
    scanned_files: list[str],
    duplicate_groups: dict[str, list[DuplicateFile]],
    destination_root: str,
) -> list[str]:
    # get list of source files - all not in destination
    # eg     # files_to_copy = {
    #     all scanned_files NOT in destination (full scan)
    #     AND not in "in_destination" list
    # }
    # print(f"<<<get_files_to_copy - destination_root: {destination_root}>>>")

    duplicates_in_destination, duplicates_not_in_destination = get_duplicate_groups_by_status(
        destination_root,
        duplicate_groups
    )

    # all source files
    source_files = [f for f in scanned_files if not
                    f.startswith(str(destination_root))]

    source_dupes_all = set([
        f.rel_path
        for df in duplicates_not_in_destination.values()
        for f in df
    ])

    # first of each duplicate group with no dupes in destination
    dupes_to_copy = [
        sorted([f.rel_path for f in d])[0]
        # d[0]
        for k, d in duplicates_not_in_destination.items()
    ]

    print(f"Duplicates to copy: {len(dupes_to_copy)}")

    # non-duplicated source files we must copy
    non_dupes_to_copy = set(source_files) - source_dupes_all

    files_to_copy = set(dupes_to_copy).union(set(non_dupes_to_copy))

    return (list(files_to_copy), duplicates_in_destination)


@dataclasses.dataclass(frozen=True)
class CopyPlan:
    """Details for planning a copy operation.

    Attributes:
        source_path: path to copy from
        destination_path: path to copy to
    """

    source_path: str
    destination_path: str


def get_copy_destination(
    destination_parent: str,
    source_path: str,
    destination_files: list[str]
) -> str:

    path = Path(source_path)
    # start by substituting the root folder
    # print(f">>> {path}")
    # print(f"=== {destination_parent}")
    naive_target = Path(destination_parent) / Path('/'.join(path.parts[1:]))
    # naive_target = Path(destination_parent) / Path('/'.join(path.parent.parts[1:]))
    new_target = None
    # get a different name if necessary
    has_conflict = True if source_path in destination_files else False
    i = 1
    while has_conflict:
        new_target = Path(naive_target.parent).joinpath(
            naive_target.stem + f" ({i})" + naive_target.suffix
        )

        has_conflict = True if new_target in destination_files else False
        i += 1

    if not new_target:
        new_target = naive_target

    return str(new_target)


def plan_copies(
    destination_root: str,
    base_path: str,
    files_to_copy: list[str],
    destination_files: list[str],
) -> list[CopyPlan]:

    copies: list[CopyPlan] = []
    for f in files_to_copy:
        dest = get_copy_destination(
            destination_root,
            f,
            destination_files
        )
        copies.append(CopyPlan(f, dest))

    return copies


def plan_deletes(
    duplicates_in_destination: dict[str, list[DuplicateFile]]
) -> list[str]:

    print(f"Groups: {len(duplicates_in_destination)}")
    files_to_delete = [
        file_path
        for duplicate_group in duplicates_in_destination.values()
        for file_path in sorted(r.rel_path for r in duplicate_group)[1:]
    ]
    # print(f"To delete: {len(files_to_delete)}")
    # files_to_keep = [
    #     sorted(r.rel_path for r in duplicate_group)[0]
    #     for duplicate_group in duplicates_in_destination.values()
    # ]
    # print(f"To keep: {len(files_to_keep)} == grp count: {len(files_to_keep)==len(duplicates_in_destination)}")

    return files_to_delete


def run_consolidation(
    conn: sqlite3.Connection,
    base_path: Path,
    destination_path: Path,
    force: bool,
) -> None:

    destination_parent: str = str(destination_path.relative_to(base_path))
    print(f"Looking for files to copy from:\n  {base_path}\n\t(except in" +
          f"{destination_parent})\nto: {destination_parent}...\n")

    cursor: sqlite3.Cursor = iter_all_files(conn)
    scanned_files = [f[1] for f in cursor]

    duplicate_groups: dict[str, list[DuplicateFile]] = build_duplicate_groups(conn)

    destination_files = [f for f in scanned_files if
                         f.startswith(str(destination_parent))]

    print(f"Scanned files: {len(scanned_files)}")
    print(f"Duplicate groups: {len(duplicate_groups)}")
    print(f"Destination files: {len(destination_files)}")

    #todo: not this
    to_copy, duplicates_in_destination = get_files_to_copy(
        scanned_files,
        duplicate_groups,
        destination_parent,
    )

    print(f"Files to copy: {len(to_copy)}")
    print(f"Duplicate groups in destination: {len(duplicates_in_destination)}")

    copy_plans = plan_copies(destination_parent, base_path, to_copy, destination_files)

    print(f"Copy plans: {len(copy_plans)}\n")
    for copy_plan in copy_plans: #[0:9]:
        print(copy_plan)

    to_delete = plan_deletes(duplicates_in_destination)
    print(f"Destination duplicates to delete: {len(to_delete)}")
    # clean up destination dupes only
    print(f"Destination initial count: {len(destination_files)}")
    print(f"Expected destination final count: {len(to_copy) + len(destination_files) - len(to_delete)}")

