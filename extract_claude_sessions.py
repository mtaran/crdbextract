#!/usr/bin/env python3
"""
Claude Code Session Extractor

Extracts Claude Code conversation sessions from ~/.claude/projects/ directory.
Sessions are stored as JSONL files containing the conversation history.
"""

import argparse
import json
import os
import pathlib
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Iterator, Optional


@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: Optional[str] = None
    tool_use: Optional[dict] = None
    tool_result: Optional[dict] = None


@dataclass
class Session:
    """A Claude Code conversation session."""
    session_id: str
    project_path: str
    cwd: str
    version: str
    messages: list
    created_at: Optional[str] = None
    slug: Optional[str] = None


def get_claude_projects_dir() -> pathlib.Path:
    """Get the Claude Code projects directory."""
    return pathlib.Path.home() / ".claude" / "projects"


def find_session_files(projects_dir: pathlib.Path) -> Iterator[pathlib.Path]:
    """Find all session JSONL files."""
    if not projects_dir.exists():
        return

    for project_dir in projects_dir.iterdir():
        if project_dir.is_dir():
            for session_file in project_dir.glob("*.jsonl"):
                # Skip agent files
                if not session_file.name.startswith("agent-"):
                    yield session_file


def parse_session(session_file: pathlib.Path) -> Optional[Session]:
    """Parse a session JSONL file into a Session object."""
    messages = []
    session_id = session_file.stem
    cwd = ""
    version = ""
    slug = None
    created_at = None

    try:
        with open(session_file, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                entry_type = entry.get("type")

                # Extract session metadata from first user message
                if entry_type == "user":
                    if not cwd:
                        cwd = entry.get("cwd", "")
                    if not version:
                        version = entry.get("version", "")
                    if not slug and entry.get("slug"):
                        slug = entry.get("slug")
                    if not created_at:
                        created_at = entry.get("timestamp")

                    # Extract message content
                    msg = entry.get("message", {})
                    content_parts = msg.get("content", [])

                    # Handle text content
                    text_content = ""
                    tool_result = None
                    for part in content_parts:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_content += part.get("text", "")
                            elif part.get("type") == "tool_result":
                                tool_result = {
                                    "tool_use_id": part.get("tool_use_id"),
                                    "content": part.get("content")
                                }

                    # Add user message
                    if text_content:
                        messages.append(Message(
                            role="user",
                            content=text_content,
                            timestamp=entry.get("timestamp")
                        ))

                    # Add tool result as separate entry
                    if tool_result:
                        messages.append(Message(
                            role="tool_result",
                            content=tool_result.get("content", ""),
                            timestamp=entry.get("timestamp"),
                            tool_result=entry.get("toolUseResult")
                        ))

                elif entry_type == "assistant":
                    msg = entry.get("message", {})
                    content_parts = msg.get("content", [])

                    text_content = ""
                    tool_use = None
                    for part in content_parts:
                        if isinstance(part, dict):
                            if part.get("type") == "text":
                                text_content += part.get("text", "")
                            elif part.get("type") == "tool_use":
                                tool_use = {
                                    "id": part.get("id"),
                                    "name": part.get("name"),
                                    "input": part.get("input")
                                }

                    messages.append(Message(
                        role="assistant",
                        content=text_content,
                        timestamp=entry.get("timestamp"),
                        tool_use=tool_use
                    ))

        if not messages:
            return None

        # Get project path from parent directory name
        project_path = session_file.parent.name.replace("-", "/")

        return Session(
            session_id=session_id,
            project_path=project_path,
            cwd=cwd,
            version=version,
            messages=messages,
            created_at=created_at,
            slug=slug
        )

    except Exception as e:
        print(f"Error parsing {session_file}: {e}", file=sys.stderr)
        return None


def session_to_dict(session: Session) -> dict:
    """Convert session to a dictionary for JSON output."""
    return {
        "session_id": session.session_id,
        "project_path": session.project_path,
        "cwd": session.cwd,
        "version": session.version,
        "created_at": session.created_at,
        "slug": session.slug,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp,
                **({"tool_use": m.tool_use} if m.tool_use else {}),
                **({"tool_result": m.tool_result} if m.tool_result else {})
            }
            for m in session.messages
        ]
    }


def format_session_readable(session: Session) -> str:
    """Format session as human-readable text."""
    lines = []
    lines.append(f"# Session: {session.session_id}")
    lines.append(f"Project: {session.project_path}")
    lines.append(f"CWD: {session.cwd}")
    lines.append(f"Created: {session.created_at}")
    if session.slug:
        lines.append(f"Slug: {session.slug}")
    lines.append("")
    lines.append("## Conversation")
    lines.append("")

    for msg in session.messages:
        if msg.role == "user":
            lines.append(f"**User:** {msg.content}")
        elif msg.role == "assistant":
            if msg.tool_use:
                tool = msg.tool_use
                lines.append(f"**Assistant:** [Tool: {tool['name']}]")
                if tool.get('input'):
                    for k, v in tool['input'].items():
                        val_str = str(v)[:100]
                        if len(str(v)) > 100:
                            val_str += "..."
                        lines.append(f"  - {k}: {val_str}")
            if msg.content:
                lines.append(f"**Assistant:** {msg.content}")
        elif msg.role == "tool_result":
            lines.append(f"**Tool Result:** {msg.content}")
        lines.append("")

    return "\n".join(lines)


def list_sessions(projects_dir: pathlib.Path) -> None:
    """List all available sessions."""
    print(f"Claude Code sessions in: {projects_dir}")
    print()

    for session_file in sorted(find_session_files(projects_dir)):
        session = parse_session(session_file)
        if session:
            msg_count = len([m for m in session.messages if m.role in ("user", "assistant") and m.content])
            first_msg = next((m.content[:50] for m in session.messages if m.role == "user" and m.content), "")
            if len(first_msg) == 50:
                first_msg += "..."

            print(f"[{session.project_path}] {session.session_id}")
            print(f"  Created: {session.created_at}")
            print(f"  Messages: {msg_count}")
            print(f"  First: \"{first_msg}\"")
            print()


def main():
    parser = argparse.ArgumentParser(
        description="Extract Claude Code conversation sessions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all sessions
  %(prog)s --list

  # Extract a specific session to JSON
  %(prog)s --session cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce --output session.json

  # Extract all sessions from a project
  %(prog)s --project /Users/mtaran/ai --output sessions.jsonl --format jsonl

  # Show session as readable text
  %(prog)s --session cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce --format text
        """
    )

    parser.add_argument(
        "--claude-dir",
        type=pathlib.Path,
        default=get_claude_projects_dir(),
        help="Path to Claude projects directory"
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List all available sessions"
    )
    parser.add_argument(
        "--session", "-s",
        help="Extract a specific session by ID"
    )
    parser.add_argument(
        "--project", "-p",
        help="Extract all sessions from a project path"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Extract all sessions"
    )
    parser.add_argument(
        "--output", "-o",
        type=pathlib.Path,
        help="Output file (stdout if not specified)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["json", "jsonl", "text"],
        default="json",
        help="Output format (default: json)"
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output"
    )

    args = parser.parse_args()

    if args.list:
        list_sessions(args.claude_dir)
        return

    sessions = []

    if args.session:
        # Find specific session
        for session_file in find_session_files(args.claude_dir):
            if session_file.stem == args.session:
                session = parse_session(session_file)
                if session:
                    sessions.append(session)
                break
        if not sessions:
            print(f"Session not found: {args.session}", file=sys.stderr)
            sys.exit(1)

    elif args.project:
        # Convert project path to directory name format
        project_dir_name = args.project.replace("/", "-")
        if project_dir_name.startswith("-"):
            pass  # Already has leading dash
        else:
            project_dir_name = "-" + project_dir_name

        project_dir = args.claude_dir / project_dir_name
        if project_dir.exists():
            for session_file in project_dir.glob("*.jsonl"):
                if not session_file.name.startswith("agent-"):
                    session = parse_session(session_file)
                    if session:
                        sessions.append(session)
        else:
            print(f"Project not found: {args.project}", file=sys.stderr)
            print(f"Looked in: {project_dir}", file=sys.stderr)
            sys.exit(1)

    elif args.all:
        for session_file in find_session_files(args.claude_dir):
            session = parse_session(session_file)
            if session:
                sessions.append(session)

    else:
        parser.print_help()
        return

    # Output
    if args.format == "text":
        output = "\n---\n\n".join(format_session_readable(s) for s in sessions)
    elif args.format == "jsonl":
        output = "\n".join(json.dumps(session_to_dict(s)) for s in sessions)
    else:  # json
        indent = 2 if args.pretty else None
        if len(sessions) == 1:
            output = json.dumps(session_to_dict(sessions[0]), indent=indent)
        else:
            output = json.dumps([session_to_dict(s) for s in sessions], indent=indent)

    if args.output:
        args.output.write_text(output)
        print(f"Wrote {len(sessions)} session(s) to {args.output}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
