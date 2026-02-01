#!/usr/bin/env python3
"""
Test harness for conversation_to_md.py using txtar-style test cases.

Test cases are stored in test_cases.txtar as pairs of .json and .md files.
The harness parses the txtar, runs the appropriate transformation, and
asserts the output matches the expected markdown.
"""

import json
import pytest
from pathlib import Path
from typing import Any

from conversation_to_md import (
    format_merged_messages,
    build_conversation_md,
    get_text_content,
    extract_message_parts,
)


TXTAR_PATH = Path(__file__).parent / "test_cases.txtar"


def parse_txtar(content: str) -> dict[str, str]:
    """
    Parse txtar format into a dict of filename -> content.

    Format:
        -- filename --
        content
        -- another_file --
        more content
    """
    files = {}
    current_file = None
    current_lines = []

    for line in content.split('\n'):
        if line.startswith('-- ') and line.endswith(' --'):
            # Save previous file (strip trailing blank/comment lines)
            if current_file is not None:
                # Remove trailing blank lines and comment lines
                while current_lines and (not current_lines[-1] or current_lines[-1].startswith('#')):
                    current_lines.pop()
                files[current_file] = '\n'.join(current_lines)
            # Start new file
            current_file = line[3:-3].strip()
            current_lines = []
        elif line.startswith('#') and current_file is None:
            # Skip comment lines before first file
            continue
        elif current_file is not None:
            # Skip comment lines between sections (lines starting with #)
            # But only if the line starts with # and we're about to hit a file marker
            # Actually, we need to keep the line for now and strip later
            current_lines.append(line)

    # Save last file
    if current_file is not None:
        # Remove trailing blank lines and comment lines
        while current_lines and (not current_lines[-1] or current_lines[-1].startswith('#')):
            current_lines.pop()
        files[current_file] = '\n'.join(current_lines)

    return files


def load_test_cases() -> dict[str, list[tuple[str, str, str]]]:
    """
    Load and group test cases by category.

    Returns dict of category -> [(test_name, json_content, md_content), ...]
    """
    content = TXTAR_PATH.read_text()
    files = parse_txtar(content)

    # Group by category and test name
    cases_by_category: dict[str, dict[str, dict[str, str]]] = {}

    for filepath, file_content in files.items():
        parts = filepath.rsplit('/', 1)
        if len(parts) != 2:
            continue
        category, filename = parts

        if filename.endswith('.json'):
            test_name = filename[:-5]
            ext = 'json'
        elif filename.endswith('.md'):
            test_name = filename[:-3]
            ext = 'md'
        else:
            continue

        if category not in cases_by_category:
            cases_by_category[category] = {}
        if test_name not in cases_by_category[category]:
            cases_by_category[category][test_name] = {}

        cases_by_category[category][test_name][ext] = file_content

    # Convert to list of tuples
    result = {}
    for category, tests in cases_by_category.items():
        result[category] = []
        for test_name, contents in sorted(tests.items()):
            if 'json' in contents and 'md' in contents:
                result[category].append((
                    test_name,
                    contents['json'].strip(),
                    contents['md']  # Don't strip - trailing newlines may be significant
                ))

    return result


# Load all test cases at module level
TEST_CASES = load_test_cases()


def get_test_ids(category: str) -> list[str]:
    """Get test IDs for parametrization."""
    return [name for name, _, _ in TEST_CASES.get(category, [])]


def get_test_params(category: str) -> list[tuple[str, str, str]]:
    """Get test parameters for parametrization."""
    return TEST_CASES.get(category, [])


# =============================================================================
# format_merged_messages tests
# =============================================================================

@pytest.mark.parametrize(
    "test_name,json_input,expected_md",
    get_test_params("format_merged"),
    ids=get_test_ids("format_merged"),
)
def test_format_merged_messages(test_name: str, json_input: str, expected_md: str):
    """Test format_merged_messages with various inputs."""
    data = json.loads(json_input)

    # Handle special case where input specifies indent
    if isinstance(data, dict) and 'indent' in data:
        indent = data['indent']
        messages = data['messages']
    else:
        indent = ""
        messages = data

    result = format_merged_messages(messages, indent=indent)

    # Normalize trailing whitespace for comparison
    result_lines = result.rstrip('\n')
    expected_lines = expected_md.rstrip('\n')

    assert result_lines == expected_lines, (
        f"\n\nTest: {test_name}\n"
        f"Expected:\n{repr(expected_lines)}\n\n"
        f"Got:\n{repr(result_lines)}"
    )


# =============================================================================
# build_conversation_md tests
# =============================================================================

@pytest.mark.parametrize(
    "test_name,json_input,expected_md",
    get_test_params("build_conv"),
    ids=get_test_ids("build_conv"),
)
def test_build_conversation_md(test_name: str, json_input: str, expected_md: str):
    """Test build_conversation_md with various inputs."""
    data = json.loads(json_input)

    # Build session_info structure expected by the function
    session_data = data['session_info']
    session_info = {
        'filepath': type('FakePath', (), {'stem': session_data['filepath_stem']})(),
        'session_id': session_data['session_id'],
        'agent_id': None,
        'is_agent': False,
        'messages': session_data['messages'],
    }

    agents = data.get('agents', [])

    result = build_conversation_md(session_info, agents)

    # Normalize trailing whitespace for comparison
    result_lines = result.rstrip('\n')
    expected_lines = expected_md.rstrip('\n')

    assert result_lines == expected_lines, (
        f"\n\nTest: {test_name}\n"
        f"Expected:\n{repr(expected_lines)}\n\n"
        f"Got:\n{repr(result_lines)}"
    )


# =============================================================================
# get_text_content tests
# =============================================================================

@pytest.mark.parametrize(
    "test_name,json_input,expected_json",
    get_test_params("get_text"),
    ids=get_test_ids("get_text"),
)
def test_get_text_content(test_name: str, json_input: str, expected_json: str):
    """Test get_text_content with various inputs."""
    content_blocks = json.loads(json_input)
    expected = json.loads(expected_json.strip())

    text, thinking, tools = get_text_content(content_blocks)

    result = {
        "text": text,
        "thinking": thinking,
        "tools": tools,
    }

    assert result == expected, (
        f"\n\nTest: {test_name}\n"
        f"Expected: {expected}\n"
        f"Got: {result}"
    )


# =============================================================================
# extract_message_parts tests
# =============================================================================

@pytest.mark.parametrize(
    "test_name,json_input,expected_json",
    get_test_params("extract_parts"),
    ids=get_test_ids("extract_parts"),
)
def test_extract_message_parts(test_name: str, json_input: str, expected_json: str):
    """Test extract_message_parts with various inputs."""
    msg = json.loads(json_input)
    expected_str = expected_json.strip()

    if expected_str == "null":
        expected = None
    else:
        expected = json.loads(expected_str)

    result = extract_message_parts(msg)

    assert result == expected, (
        f"\n\nTest: {test_name}\n"
        f"Expected: {expected}\n"
        f"Got: {result}"
    )


# =============================================================================
# Txtar parsing tests (meta-tests)
# =============================================================================

class TestTxtarParsing:
    """Tests for the txtar parsing itself."""

    def test_parse_simple(self):
        content = """-- file1.txt --
hello
-- file2.txt --
world"""
        files = parse_txtar(content)
        assert files == {
            "file1.txt": "hello",
            "file2.txt": "world",
        }

    def test_parse_with_comments(self):
        content = """# This is a comment
# Another comment
-- file.txt --
content"""
        files = parse_txtar(content)
        assert files == {"file.txt": "content"}

    def test_parse_multiline_content(self):
        content = """-- file.txt --
line1
line2
line3"""
        files = parse_txtar(content)
        assert files == {"file.txt": "line1\nline2\nline3"}

    def test_parse_with_path(self):
        content = """-- dir/subdir/file.txt --
content"""
        files = parse_txtar(content)
        assert files == {"dir/subdir/file.txt": "content"}

    def test_test_cases_loaded(self):
        """Verify test cases were loaded correctly."""
        assert "format_merged" in TEST_CASES
        assert "build_conv" in TEST_CASES
        assert "get_text" in TEST_CASES
        assert "extract_parts" in TEST_CASES

        # Check we have a reasonable number of tests
        assert len(TEST_CASES["format_merged"]) >= 10
        assert len(TEST_CASES["build_conv"]) >= 3
        assert len(TEST_CASES["get_text"]) >= 5
        assert len(TEST_CASES["extract_parts"]) >= 5


# =============================================================================
# Additional edge case tests (not easily expressed in txtar)
# =============================================================================

class TestEdgeCases:
    """Edge cases that are easier to test directly in Python."""

    def test_get_text_content_none_input(self):
        """Test get_text_content with None input."""
        text, thinking, tools = get_text_content(None)
        assert text == ""
        assert thinking == ""
        assert tools == []

    def test_format_merged_empty_list(self):
        """Test format_merged_messages with empty list."""
        result = format_merged_messages([])
        assert result == ""

