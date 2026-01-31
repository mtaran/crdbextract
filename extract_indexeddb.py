#!/usr/bin/env python3
"""
Chrome IndexedDB Extraction Tool

Extracts data from Chrome's IndexedDB storage (LevelDB format) to JSON.
"""

import argparse
import json
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Any, Iterator, Optional

try:
    from ccl_chromium_reader import ccl_chromium_indexeddb as idb
except ImportError:
    print("Error: ccl_chromium_reader not installed")
    print("Install with: pip install git+https://github.com/cclgroupltd/ccl_chromium_reader.git")
    sys.exit(1)


def copy_to_temp(source_path: pathlib.Path) -> pathlib.Path:
    """Copy a LevelDB directory to temp to avoid lock issues with running Chrome."""
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="indexeddb_"))
    dest_path = temp_dir / source_path.name
    shutil.copytree(source_path, dest_path)
    return dest_path


def get_chrome_profiles(chrome_path: pathlib.Path) -> Iterator[tuple[str, pathlib.Path]]:
    """Find all Chrome profiles and return (profile_name, profile_path) tuples."""
    if not chrome_path.exists():
        return

    # Check for Default profile
    default_profile = chrome_path / "Default"
    if default_profile.exists():
        yield ("Default", default_profile)

    # Check for numbered profiles (Profile 1, Profile 2, etc.)
    for profile_dir in chrome_path.iterdir():
        if profile_dir.is_dir() and profile_dir.name.startswith("Profile "):
            yield (profile_dir.name, profile_dir)

    # Check for Guest Profile
    guest_profile = chrome_path / "Guest Profile"
    if guest_profile.exists():
        yield ("Guest Profile", guest_profile)


def get_default_chrome_path() -> pathlib.Path:
    """Get the default Chrome IndexedDB path for the current platform."""
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support/Google/Chrome"
    elif sys.platform == "win32":
        return pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data"
    else:  # Linux
        return pathlib.Path.home() / ".config/google-chrome"


def find_indexeddb_dirs(chrome_path: pathlib.Path) -> Iterator[pathlib.Path]:
    """Find all IndexedDB LevelDB directories under the Chrome profile path."""
    if not chrome_path.exists():
        return

    for idb_dir in chrome_path.rglob("*.indexeddb.leveldb"):
        if idb_dir.is_dir():
            yield idb_dir


def serialize_value(value: Any) -> Any:
    """Convert a value to JSON-serializable format."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode('utf-8')
        except UnicodeDecodeError:
            return f"<bytes:{len(value)}>"
    if isinstance(value, dict):
        return {str(k): serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    # For other types, convert to string
    return str(value)


def extract_database(leveldb_path: pathlib.Path, include_deleted: bool = False, safe_copy: bool = False) -> dict:
    """Extract all data from an IndexedDB LevelDB directory.

    Args:
        leveldb_path: Path to the IndexedDB LevelDB directory
        include_deleted: Include deleted records
        safe_copy: Copy database to temp directory first (avoids Chrome lock issues)
    """
    result = {
        "path": str(leveldb_path),
        "origin": leveldb_path.name.replace(".indexeddb.leveldb", ""),
        "databases": []
    }

    work_path = leveldb_path
    temp_dir = None

    try:
        if safe_copy:
            work_path = copy_to_temp(leveldb_path)
            temp_dir = work_path.parent

        raw_db = idb.IndexedDb(work_path)
    except Exception as e:
        result["error"] = str(e)
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return result

    for db_id in raw_db.global_metadata.db_ids:
        db_data = {
            "name": db_id.name,
            "id": db_id.dbid_no,
            "origin": db_id.origin,
            "object_stores": []
        }

        try:
            wrapped_db = idb.WrappedDatabase(raw_db, db_id)
            store_names = list(wrapped_db.object_store_names)

            for store_name in store_names:
                store_data = {
                    "name": store_name,
                    "records": []
                }

                try:
                    store = wrapped_db.get_object_store_by_name(store_name)
                    for record in store.iterate_records():
                        # Skip deleted records unless requested
                        if hasattr(record, 'state') and record.state == 'deleted' and not include_deleted:
                            continue

                        record_data = {
                            "key": serialize_value(record.key.value if hasattr(record.key, 'value') else str(record.key)),
                            "value": serialize_value(record.value)
                        }

                        if hasattr(record, 'state'):
                            record_data["state"] = str(record.state)

                        store_data["records"].append(record_data)

                except Exception as e:
                    store_data["error"] = str(e)

                db_data["object_stores"].append(store_data)

        except Exception as e:
            db_data["error"] = str(e)

        result["databases"].append(db_data)

    # Cleanup temp directory if we created one
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return result


def list_databases(chrome_path: pathlib.Path) -> None:
    """List all IndexedDB databases found."""
    print(f"Scanning: {chrome_path}")
    print()

    for idb_dir in find_indexeddb_dirs(chrome_path):
        origin = idb_dir.name.replace(".indexeddb.leveldb", "")
        profile = idb_dir.parent.parent.name

        try:
            raw_db = idb.IndexedDb(idb_dir)
            db_count = len(raw_db.global_metadata.db_ids)
            db_names = [d.name for d in raw_db.global_metadata.db_ids]
        except Exception as e:
            db_count = 0
            db_names = [f"Error: {e}"]

        print(f"[{profile}] {origin}")
        print(f"  Path: {idb_dir}")
        print(f"  Databases ({db_count}): {', '.join(db_names)}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract data from Chrome IndexedDB storage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all IndexedDB databases
  %(prog)s --list

  # Extract a specific database to JSON
  %(prog)s --path "/path/to/https_example.com_0.indexeddb.leveldb" --output data.json

  # Extract all databases from a Chrome profile
  %(prog)s --all --output all_data.json
        """
    )

    parser.add_argument(
        "--chrome-path",
        type=pathlib.Path,
        default=get_default_chrome_path(),
        help="Path to Chrome user data directory"
    )
    parser.add_argument(
        "--path", "-p",
        type=pathlib.Path,
        help="Path to specific IndexedDB LevelDB directory"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available IndexedDB databases"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Extract all IndexedDB databases"
    )
    parser.add_argument(
        "--output", "-o",
        type=pathlib.Path,
        help="Output JSON file (stdout if not specified)"
    )
    parser.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include deleted records"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )
    parser.add_argument(
        "--safe-copy",
        action="store_true",
        help="Copy database to temp directory before reading (avoids Chrome lock issues)"
    )
    parser.add_argument(
        "--profile",
        help="Chrome profile name to use (Default, Profile 1, etc.)"
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List all Chrome profiles"
    )

    args = parser.parse_args()

    # Handle --list-profiles
    if args.list_profiles:
        print(f"Chrome profiles in: {args.chrome_path}")
        for profile_name, profile_path in get_chrome_profiles(args.chrome_path):
            idb_path = profile_path / "IndexedDB"
            idb_count = len(list(idb_path.glob("*.indexeddb.leveldb"))) if idb_path.exists() else 0
            print(f"  {profile_name}: {idb_count} IndexedDB origins")
        return

    # Determine effective chrome path (with profile if specified)
    effective_path = args.chrome_path
    if args.profile:
        profile_path = args.chrome_path / args.profile
        if not profile_path.exists():
            print(f"Error: Profile '{args.profile}' not found at {profile_path}", file=sys.stderr)
            sys.exit(1)
        effective_path = profile_path

    if args.list:
        list_databases(effective_path)
        return

    if args.path:
        # Extract specific database
        result = extract_database(args.path, args.include_deleted, args.safe_copy)
        results = [result]
    elif args.all:
        # Extract all databases
        results = []
        for idb_dir in find_indexeddb_dirs(effective_path):
            print(f"Extracting: {idb_dir.name}", file=sys.stderr)
            result = extract_database(idb_dir, args.include_deleted, args.safe_copy)
            results.append(result)
    else:
        parser.print_help()
        return

    # Output
    indent = 2 if args.pretty else None
    output = json.dumps(results, indent=indent, default=str)

    if args.output:
        args.output.write_text(output)
        print(f"Wrote {len(results)} database(s) to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
