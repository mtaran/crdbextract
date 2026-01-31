#!/usr/bin/env python3
"""
Claude Code Session Extractor

Copies raw Claude Code session JSONL files from ~/.claude/projects/ to a specified directory.
"""

import argparse
import pathlib
import shutil
import sys
from typing import Iterator


def get_claude_projects_dir() -> pathlib.Path:
    """Get the Claude Code projects directory."""
    return pathlib.Path.home() / ".claude" / "projects"


def find_session_files(projects_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Find all session JSONL files (including agent- files)."""
    if not projects_dir.exists():
        return

    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for session_file in project_dir.glob("*.jsonl"):
                yield session_file


def main():
    parser = argparse.ArgumentParser(
        description="Copy raw Claude Code session JSONL files to a directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all session files
  %(prog)s --list

  # Copy all sessions to a directory
  %(prog)s --output ./sessions/

  # Copy sessions from a specific project
  %(prog)s --project /Users/mtaran/myproject --output ./sessions/
        """
    )

    parser.add_argument(
        "--claude-dir",
        type=pathlib.Path,
        default=get_claude_projects_dir(),
        help="Path to Claude projects directory (default: ~/.claude/projects)"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available session files"
    )
    parser.add_argument(
        "--project", "-p",
        help="Only copy sessions from a specific project path"
    )
    parser.add_argument(
        "--output", "-o",
        type=pathlib.Path,
        help="Output directory to copy JSONL files to"
    )

    args = parser.parse_args()

    if args.list:
        print(f"Claude Code sessions in: {args.claude_dir}")
        print()
        for session_file in sorted(find_session_files(args.claude_dir)):
            project_name = session_file.parent.name
            print(f"  {project_name}/{session_file.name}")
        return

    if not args.output:
        parser.print_help()
        print("\nError: --output directory is required", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)

    # Find files to copy
    files_to_copy = []

    if args.project:
        # Convert project path to directory name format
        project_dir_name = args.project.replace("/", "-")
        if not project_dir_name.startswith("-"):
            project_dir_name = "-" + project_dir_name

        project_dir = args.claude_dir / project_dir_name
        if project_dir.exists():
            files_to_copy = list(project_dir.glob("*.jsonl"))
        else:
            print(f"Project not found: {args.project}", file=sys.stderr)
            print(f"Looked in: {project_dir}", file=sys.stderr)
            sys.exit(1)
    else:
        files_to_copy = list(find_session_files(args.claude_dir))

    # Copy files
    copied = 0
    for session_file in files_to_copy:
        project_name = session_file.parent.name
        # Prefix with project name to avoid collisions
        dest_name = f"{project_name}_{session_file.name}"
        dest_path = args.output / dest_name
        shutil.copy2(session_file, dest_path)
        copied += 1
        print(f"Copied: {dest_name}")

    print(f"\nCopied {copied} file(s) to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
