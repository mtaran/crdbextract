#!/usr/bin/env python3
"""
Convert Claude Code conversation JSONL files to readable Markdown.
Groups main sessions with their sub-agents, indenting agent content.
"""

import json
import os
import re
import sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def parse_jsonl(filepath: Path) -> list[dict]:
    """Parse a JSONL file, returning list of message objects."""
    messages = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"Warning: Failed to parse line {line_num} in {filepath}: {e}", file=sys.stderr)
    return messages


def extract_session_info(filepath: Path) -> dict:
    """Extract session metadata from a JSONL file."""
    messages = parse_jsonl(filepath)
    if not messages:
        return None

    # Find first message with relevant info
    for msg in messages:
        session_id = msg.get('sessionId')
        agent_id = msg.get('agentId')
        if session_id:
            return {
                'filepath': filepath,
                'session_id': session_id,
                'agent_id': agent_id,
                'is_agent': agent_id is not None,
                'messages': messages
            }
    return None


def _format_tool_call(tool_name: str, tool_input: dict) -> str:
    """Format a tool call for display."""
    # Tools that show file_path
    if tool_name in ('Read', 'Write', 'Edit'):
        path = tool_input.get('file_path', '')
        return f"[{tool_name}] {path}"

    # Tools that show pattern
    if tool_name in ('Glob', 'Grep'):
        pattern = tool_input.get('pattern', '')
        return f"[{tool_name}] {pattern}"

    # Special cases
    if tool_name == 'Bash':
        return "[Bash]"

    if tool_name == 'Task':
        desc = tool_input.get('description', '')
        agent_type = tool_input.get('subagent_type', '')
        return f"[Task] {desc} ({agent_type})"

    if tool_name == 'TodoWrite':
        todos = tool_input.get('todos', [])
        if todos:
            todo_summary = "; ".join(
                f"{t.get('status', '?')[0].upper()}: {t.get('content', '')[:40]}"
                for t in todos[:5]
            )
            if len(todos) > 5:
                todo_summary += f" (+{len(todos) - 5} more)"
            return f"[TodoWrite] {todo_summary}"
        return "[TodoWrite]"

    if tool_name == 'WebFetch':
        url = tool_input.get('url', '')
        return f"[WebFetch] {url}"

    if tool_name == 'WebSearch':
        query = tool_input.get('query', '')
        return f"[WebSearch] {query}"

    # Default: just the tool name
    return f"[{tool_name}]"


def get_text_content(content_blocks: list) -> tuple[str, str, list[str]]:
    """
    Extract text, thinking, and tool calls from content blocks.
    Returns (text, thinking, tool_calls)
    """
    text_parts = []
    thinking_parts = []
    tool_calls = []

    if not content_blocks:
        return "", "", []

    for block in content_blocks:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict):
            block_type = block.get('type', '')

            if block_type == 'text':
                text_parts.append(block.get('text', ''))
            elif block_type == 'thinking':
                thinking_parts.append(block.get('thinking', ''))
            elif block_type == 'tool_use':
                tool_name = block.get('name', 'unknown')
                tool_input = block.get('input', {})
                tool_calls.append(_format_tool_call(tool_name, tool_input))
            elif block_type == 'tool_result':
                # Skip tool results in output
                pass

    return '\n'.join(text_parts), '\n'.join(thinking_parts), tool_calls


def extract_message_parts(msg: dict) -> dict:
    """Extract the parts of a message for later formatting."""
    msg_type = msg.get('type', '')

    # Skip non-message types
    if msg_type in ('queue-operation', 'file-history-snapshot'):
        return None

    message_data = msg.get('message', {})
    role = message_data.get('role', msg_type)
    content = message_data.get('content', [])

    # Handle string content
    if isinstance(content, str):
        content = [{'type': 'text', 'text': content}]

    text, thinking, tool_calls = get_text_content(content)

    # Check if it's a tool result
    if role == 'user':
        is_tool_result = any(
            isinstance(c, dict) and c.get('type') == 'tool_result'
            for c in content
        )
        if is_tool_result:
            return None

    # Skip empty messages
    if not text and not thinking and not tool_calls:
        return None

    model = message_data.get('model', '')
    model_short = model.split('-')[1] if '-' in model else model

    # Clean up text
    if text:
        text = re.sub(r'<ide_selection>.*?</ide_selection>', '[IDE Selection]', text, flags=re.DOTALL)
        text = re.sub(r'<ide_opened_file>.*?</ide_opened_file>', '', text, flags=re.DOTALL)
        text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
        text = text.strip()

    return {
        'role': role,
        'model': model_short,
        'text': text,
        'thinking': thinking,
        'tool_calls': tool_calls,
    }


def format_merged_messages(messages: list[dict], indent: str = "") -> str:
    """
    Format messages, merging consecutive assistant tool-call-only blocks into
    the preceding text block.
    """
    lines = []
    i = 0

    while i < len(messages):
        msg = messages[i]
        parts = extract_message_parts(msg)

        if parts is None:
            i += 1
            continue

        if parts['role'] == 'user':
            lines.append(f"{indent}### User")
            lines.append("")
            if parts['text']:
                for line in parts['text'].split('\n'):
                    lines.append(f"{indent}{line}")
                lines.append("")
            i += 1

        elif parts['role'] == 'assistant':
            model = parts['model']

            # Output thinking if present
            if parts['thinking']:
                lines.append(f"{indent}### Assistant ({model})")
                lines.append("")
                for line in parts['thinking'].split('\n'):
                    lines.append(f"{indent}> {line}")
                lines.append(f"{indent}>")
                lines.append("")

            # Output text if present
            if parts['text']:
                if not parts['thinking']:  # Don't repeat header
                    lines.append(f"{indent}### Assistant ({model})")
                    lines.append("")
                for line in parts['text'].split('\n'):
                    lines.append(f"{indent}{line}")
                lines.append("")

            # Collect this message's tools plus any following tool-only messages
            collected_tools = list(parts['tool_calls'])
            i += 1

            # Look ahead for consecutive tool-only assistant messages
            while i < len(messages):
                next_parts = extract_message_parts(messages[i])
                if next_parts is None:
                    i += 1
                    continue
                if next_parts['role'] != 'assistant':
                    break
                # If this assistant message has text or thinking, stop merging
                if next_parts['text'] or next_parts['thinking']:
                    break
                # Tool-only message - merge it
                collected_tools.extend(next_parts['tool_calls'])
                if next_parts['model']:
                    model = next_parts['model']
                i += 1

            # Output collected tools
            if collected_tools:
                # If we had no text/thinking, we need a header
                if not parts['text'] and not parts['thinking']:
                    lines.append(f"{indent}### Assistant ({model})")
                    lines.append("")
                for tc in collected_tools:
                    lines.append(f"{indent}- {tc}")
                lines.append("")
        else:
            i += 1

    return '\n'.join(lines)


def get_first_timestamp(messages: list[dict]) -> str:
    """Get the first timestamp from messages."""
    for msg in messages:
        ts = msg.get('timestamp', '')
        if ts:
            try:
                dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                return dt.strftime('%Y-%m-%d %H:%M')
            except:
                return ts[:16]
    return "unknown"


def build_conversation_md(session_info: dict, agents: list[dict]) -> str:
    """Build markdown for a conversation including its agents."""
    lines = []

    filepath = session_info['filepath']
    session_id = session_info['session_id']

    # Get conversation start time
    start_time = get_first_timestamp(session_info['messages'])

    # Get working directory from messages
    cwd = ""
    for msg in session_info['messages']:
        if msg.get('cwd'):
            cwd = msg['cwd']
            break

    lines.append(f"# Conversation: {filepath.stem}")
    lines.append("")
    lines.append(f"**Session ID:** `{session_id}`")
    lines.append(f"**Started:** {start_time}")
    if cwd:
        lines.append(f"**Working Directory:** `{cwd}`")
    lines.append(f"**Agents spawned:** {len(agents)}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Build a map of agent messages by agentId
    agent_messages_by_id = {}
    for agent in agents:
        agent_id = agent['agent_id']
        agent_messages_by_id[agent_id] = agent['messages']

    # Track which agents we've already inlined
    inlined_agents = set()

    # Process main session messages with agent inlining
    main_messages = session_info['messages']

    # Collect messages into chunks, splitting at agent spawn points
    chunk = []
    for msg in main_messages:
        chunk.append(msg)

        # Check if this message spawns an agent
        tool_result = msg.get('toolUseResult', {})
        spawned_agent_id = (
            tool_result.get('agentId')
            if isinstance(tool_result, dict)
            else None
        )

        if spawned_agent_id:
            # Format the chunk up to and including the spawn message
            formatted = format_merged_messages(chunk)
            if formatted.strip():
                lines.append(formatted)
            chunk = []

            # Inline the agent if available
            if spawned_agent_id in agent_messages_by_id and spawned_agent_id not in inlined_agents:
                inlined_agents.add(spawned_agent_id)

                desc = tool_result.get('description', '')
                lines.append("> ---")
                lines.append(f"> **[Agent: {spawned_agent_id}]** {desc}")
                lines.append(">")

                agent_formatted = format_merged_messages(
                    agent_messages_by_id[spawned_agent_id],
                    indent="> "
                )
                if agent_formatted.strip():
                    lines.append(agent_formatted)

                lines.append(f"> **[Agent: {spawned_agent_id}]** ended")
                lines.append("> ---")
                lines.append("")

    # Format any remaining messages after the last agent spawn
    if chunk:
        formatted = format_merged_messages(chunk)
        if formatted.strip():
            lines.append(formatted)

    # Add any agents that weren't inlined
    for agent in agents:
        agent_id = agent['agent_id']
        if agent_id not in inlined_agents:
            lines.append(f"## Agent: {agent_id} (not inlined)")
            lines.append("")
            agent_formatted = format_merged_messages(agent['messages'], indent="> ")
            if agent_formatted.strip():
                lines.append(agent_formatted)

    return '\n'.join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Convert Claude Code JSONL to Markdown')
    parser.add_argument('input_dir', type=Path, help='Directory containing JSONL files')
    parser.add_argument('output_dir', type=Path, help='Directory to write Markdown files')
    parser.add_argument('--session', type=str, help='Only process specific session ID (partial match)')
    args = parser.parse_args()

    input_dir = args.input_dir
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all sessions and agents
    sessions = {}  # session_id -> session_info
    agents_by_parent = defaultdict(list)  # parent_session_id -> [agent_info, ...]

    for filepath in sorted(input_dir.glob('*.jsonl')):
        if filepath.stat().st_size == 0:
            continue

        info = extract_session_info(filepath)
        if not info:
            continue

        if info['is_agent']:
            # This is an agent - group by parent session
            agents_by_parent[info['session_id']].append(info)
        else:
            # This is a main session
            sessions[info['session_id']] = info

    print(f"Found {len(sessions)} main sessions and {sum(len(v) for v in agents_by_parent.values())} agents")

    # Process each main session
    processed = 0
    for session_id, session_info in sessions.items():
        # Filter by session if specified
        if args.session and args.session not in session_id:
            continue

        agents = agents_by_parent.get(session_id, [])

        # Generate markdown
        md_content = build_conversation_md(session_info, agents)

        # Write to file
        output_filename = f"{session_info['filepath'].stem}.md"
        output_path = output_dir / output_filename

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md_content)

        processed += 1
        print(f"Wrote: {output_path.name} ({len(agents)} agents)")

    print(f"\nProcessed {processed} conversations")


if __name__ == '__main__':
    main()
