# crdbextract

Tools for extracting data from Chrome's IndexedDB storage and Claude Code sessions.

## Features

- **Chrome IndexedDB Extraction**: Extract data from Chrome's LevelDB-based IndexedDB storage
- **Multi-Profile Support**: Work with multiple Chrome profiles
- **Safe Extraction**: Copy databases before reading to avoid Chrome file locks
- **Claude Code Sessions**: Extract conversation history from Claude Code's local storage

## Installation

```bash
# Clone the repository
git clone https://github.com/mtaran/crdbextract.git
cd crdbextract

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Chrome IndexedDB Extraction

```bash
# List all IndexedDB databases
python extract_indexeddb.py --list

# List Chrome profiles
python extract_indexeddb.py --list-profiles

# Extract a specific database
python extract_indexeddb.py --path "/path/to/https_example.com_0.indexeddb.leveldb" --pretty

# Extract with safe copy (avoids Chrome locks)
python extract_indexeddb.py --path "/path/to/db" --safe-copy --output data.json

# Extract from a specific profile
python extract_indexeddb.py --profile "Profile 1" --list

# Extract all databases
python extract_indexeddb.py --all --output all_data.json
```

### Claude Code Session Extraction

Claude Code stores conversation sessions locally at `~/.claude/projects/`.

```bash
# List all Claude Code sessions
python extract_claude_sessions.py --list

# Extract a specific session as JSON
python extract_claude_sessions.py --session <session-id> --pretty

# Extract as human-readable text
python extract_claude_sessions.py --session <session-id> --format text

# Extract all sessions from a project
python extract_claude_sessions.py --project /path/to/project --format jsonl

# Extract all sessions
python extract_claude_sessions.py --all --output sessions.json
```

## Chrome IndexedDB Location

| Platform | Path |
|----------|------|
| macOS | `~/Library/Application Support/Google/Chrome/Default/IndexedDB/` |
| Windows | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\IndexedDB\` |
| Linux | `~/.config/google-chrome/Default/IndexedDB/` |

Each origin gets a `<origin>_0.indexeddb.leveldb` directory containing LevelDB files.

## How It Works

Chrome stores IndexedDB data in LevelDB format with:
- V8/Blink serialization for JavaScript values
- Snappy compression for data blocks
- Write-ahead logging for durability

This tool uses [ccl_chromium_reader](https://github.com/cclgroupltd/ccl_chromium_reader) to parse the LevelDB format and deserialize the stored values.

## Output Format

### IndexedDB Output
```json
{
  "path": "/path/to/database.indexeddb.leveldb",
  "origin": "https_example.com_0",
  "databases": [
    {
      "name": "myDatabase",
      "id": 1,
      "object_stores": [
        {
          "name": "myStore",
          "records": [
            {"key": "key1", "value": {"data": "value"}}
          ]
        }
      ]
    }
  ]
}
```

### Claude Session Output
```json
{
  "session_id": "uuid",
  "project_path": "/path/to/project",
  "cwd": "/working/directory",
  "messages": [
    {"role": "user", "content": "Hello", "timestamp": "..."},
    {"role": "assistant", "content": "Hi!", "timestamp": "..."}
  ]
}
```

## Notes

- **Chrome must be closed** for reliable extraction, or use `--safe-copy`
- Recent writes may be in WAL (`.log` files) not yet compacted to `.ldb` files
- Some complex JavaScript objects (Blobs, Files) may not fully deserialize

## Credits

- [ccl_chromium_reader](https://github.com/cclgroupltd/ccl_chromium_reader) - LevelDB and IndexedDB parsing
- [dfindexeddb](https://github.com/google/dfindexeddb) - Alternative Google tool for forensic analysis

## License

MIT
