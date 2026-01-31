# Chrome IndexedDB Extraction Tool - Research Log

## Project Goal
Build a tool to extract contents of Chrome's IndexedDB from local Chrome installations.

## Chrome IndexedDB Storage Structure

### Location on macOS
```
~/Library/Application Support/Google/Chrome/Default/IndexedDB/
```

For other profiles:
```
~/Library/Application Support/Google/Chrome/Profile N/IndexedDB/
```

### Directory Structure
IndexedDB stores are organized by origin:
- `https_example.com_0.indexeddb.leveldb/` - LevelDB storage for example.com
- `https_example.com_0.indexeddb.blob/` - Blob storage (for large binary data)

Each LevelDB directory contains:
- `*.ldb` - Sorted table files (SST files)
- `*.log` - Write-ahead log files
- `MANIFEST-*` - Manifest files tracking database state
- `CURRENT` - Points to current manifest
- `LOCK` - Lock file
- `LOG` - Human-readable log

### Sample databases found on test machine:
- Slack (`https_app.slack.com_0`)
- Claude.ai (`https_claude.ai_0`)
- Google Docs/Drive
- GitHub
- MDN demo (`https_mdn.github.io_0`)
- Progressier demo (`https_progressier.com_0`)

## Existing Tools Evaluated

### 1. dfindexeddb (Google)
**Source:** https://github.com/google/dfindexeddb
**PyPI:** https://pypi.org/project/dfindexeddb/

**Installation:**
```bash
pip install python-snappy zstd click  # dependencies
pip install --no-deps dfindexeddb
```

**Usage:**
```bash
dfindexeddb db -s "/path/to/indexeddb.leveldb" --format chrome --use_manifest
```

**Pros:**
- Official Google tool
- Outputs JSON/JSONL format
- Can parse from individual .ldb or .log files
- Includes record offsets for forensic verification
- Recovers deleted records from log files

**Cons:**
- Strict dependency version requirements (python-snappy==0.6.1)
- Output is verbose with lots of metadata
- Requires post-processing to get human-readable data

**Sample Output:**
```json
{
  "__type__": "IndexedDBRecord",
  "key": {
    "__type__": "ObjectStoreDataKey",
    "encoded_user_key": {"type": 1, "value": "0"}
  },
  "value": {
    "__type__": "ObjectStoreDataValue",
    "value": {"minChannelUpdated": 1765099257693.0}
  }
}
```

### 2. ccl_chromium_reader (CCL Group)
**Source:** https://github.com/cclgroupltd/ccl_chromium_reader
**Also:** https://github.com/obsidianforensics/ccl_chrome_indexeddb

**Installation:**
```bash
pip install git+https://github.com/cclgroupltd/ccl_chromium_reader.git
```

**Usage (Python API):**
```python
from ccl_chromium_reader import ccl_chromium_indexeddb as idb
import pathlib

path = pathlib.Path('/path/to/indexeddb.leveldb')
raw_db = idb.IndexedDb(path)

for db_id in raw_db.global_metadata.db_ids:
    wrapped_db = idb.WrappedDatabase(raw_db, db_id)
    for store_name in wrapped_db.object_store_names:
        store = wrapped_db.get_object_store_by_name(store_name)
        for record in store.iterate_records():
            print(record.key, record.value)
```

**Pros:**
- Pure Python implementation
- Includes V8/Blink value deserialization
- Well-structured object-oriented API
- Can recover deleted records
- Part of larger forensics toolkit

**Cons:**
- API documentation is sparse
- Not published to PyPI
- Some edge cases may not be handled

**Sample Output:**
```
Database: objectStore-T04TJB7UJHW-U09LXC79K2A
  Object Store: sundryStorage
    <IdbKey 0> => {'minChannelUpdated': 1765099257693.0}
```

## Test Results

### MDN Demo (https://mdn.github.io/dom-examples/indexeddb-api/index.html)
- Database created: `mdn-demo-indexeddb-epublications`
- Object stores: `publications`
- Records: 0 (data was not persisted or was deleted)

Note: This demo may require adding items and ensuring Chrome persists them to disk.

### Progressier Demo (https://progressier.com/pwa-capabilities/indexeddb-demo)
- Database found but appears empty
- May need interaction to populate data

### Slack
- Multiple databases found
- Successfully extracted data including:
  - `sundryStorage` with channel update timestamps
  - `reduxPersistenceStore`

### Claude.ai
- Multiple Firebase-related databases found
- Successfully extracted:
  - Firebase messaging tokens
  - Firebase installations data
  - Firebase heartbeat data

## Next Steps

1. **Build wrapper tool** - Create a unified CLI that:
   - Auto-discovers Chrome profiles and IndexedDB locations
   - Lists all available databases
   - Extracts to JSON/CSV format
   - Handles both tools (dfindexeddb for raw forensics, ccl for structured access)

2. **Handle edge cases**:
   - Multiple Chrome profiles
   - Chrome locked database files (when Chrome is running)
   - Blob storage extraction
   - Large databases (pagination)

3. **Testing**:
   - Create test databases using the MDN/Progressier demos
   - Verify extracted data matches what's shown in DevTools

4. **Documentation**:
   - Usage examples
   - Data format specifications
   - Forensic considerations (chain of custody, hashing)

## Technical Notes

### Chrome must be closed
Chrome locks IndexedDB files while running. For reliable extraction:
- Close Chrome completely
- Or copy the IndexedDB directory first

### Data may be in WAL
Recent writes may not be in `.ldb` files but in `.log` (write-ahead log).
dfindexeddb handles this with `--use_manifest` flag.

### V8/Blink Serialization
IndexedDB values are serialized using V8's structured clone algorithm.
Both tools handle deserialization, but complex objects (Blobs, Files) may need special handling.

## Custom Tool Created: extract_indexeddb.py

A unified extraction tool was created that wraps `ccl_chromium_reader` with a clean CLI.

### Installation
```bash
python3 -m venv venv
source venv/bin/activate
pip install git+https://github.com/cclgroupltd/ccl_chromium_reader.git
```

### Usage

**List all databases:**
```bash
python extract_indexeddb.py --list
```

**Extract specific database:**
```bash
python extract_indexeddb.py --path "/path/to/https_example.com_0.indexeddb.leveldb" --pretty
```

**Extract all databases:**
```bash
python extract_indexeddb.py --all --output all_data.json
```

**List Chrome profiles:**
```bash
python extract_indexeddb.py --list-profiles
```

**Extract from specific profile:**
```bash
python extract_indexeddb.py --profile "Profile 8" --list
```

**Safe extraction (copy first to avoid Chrome locks):**
```bash
python extract_indexeddb.py --path "/path/to/db" --safe-copy --pretty
```

### Features
- **File Locking Handling:** `--safe-copy` copies database to temp before reading (avoids Chrome lock issues)
- **Multi-Profile Support:** `--profile` to specify Chrome profile, `--list-profiles` to see all profiles
- **Flexible Output:** JSON, pretty-printed, or to file

### Sample Output
```json
[
  {
    "path": "/path/to/https_app.slack.com_0.indexeddb.leveldb",
    "origin": "https_app.slack.com_0",
    "databases": [
      {
        "name": "objectStore-T04TJB7UJHW-U09LXC79K2A",
        "id": 2,
        "object_stores": [
          {
            "name": "sundryStorage",
            "records": [
              {
                "key": "0",
                "value": {"minChannelUpdated": 1765099257693.0}
              }
            ]
          }
        ]
      }
    ]
  }
]
```

## Claude Code Session Storage

**Important Discovery:** Claude Code sessions are NOT stored in Chrome's IndexedDB.

When using Claude Code via VSCode (desktop or web tunnel), sessions are stored locally:

### Location
```
~/.claude/projects/<project-path-with-dashes>/<session-id>.jsonl
```

Example:
```
~/.claude/projects/-Users-mtaran-ai/cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce.jsonl
```

### Format
Sessions are stored as JSONL (JSON Lines) with entries for:
- `type: "user"` - User messages with content, cwd, version
- `type: "assistant"` - Assistant responses with tool_use or text content
- `type: "file-history-snapshot"` - File change tracking
- `type: "queue-operation"` - Internal queue state

### VSCode IndexedDB Relationship
The VSCode IndexedDB (at `https_vscode.dev_0.indexeddb.leveldb`) only stores:
- Session ID reference in `memento/workbench.parts.editor`
- Extension settings in `Anthropic.claude-code` keys
- The actual conversation content is on the server (local machine for tunnels)

### Session Extraction Tool
Created `extract_claude_sessions.py` to extract sessions:

```bash
# List all sessions
python extract_claude_sessions.py --list

# Extract specific session as JSON
python extract_claude_sessions.py --session cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce --pretty

# Extract as human-readable text
python extract_claude_sessions.py --session cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce --format text

# Extract all sessions from a project
python extract_claude_sessions.py --project /Users/mtaran/ai --format jsonl
```

### Verified Session Extraction
Successfully extracted session `cc9d9f84-79ab-4a50-a4c2-77ecaedf46ce`:
- User: "write a test.txt wile with \"hello from claude\" in it"
- Assistant used Write tool to create test.txt
- Result: File created with "hello from claude" content

## Files Created

- `LOG.md` - This research log
- `extract_indexeddb.py` - Chrome IndexedDB extraction CLI tool
- `extract_claude_sessions.py` - Claude Code session extraction tool
- `test_ccl.py` - Test script for ccl_chromium_reader
- `venv/` - Python virtual environment with dependencies

## References

- [Chrome IndexedDB Implementation](https://source.chromium.org/chromium/chromium/src/+/main:content/browser/indexed_db/)
- [CCL Blog Post on IndexedDB](https://www.cclsolutionsgroup.com/post/indexeddb-on-chromium)
- [LevelDB Format](https://github.com/google/leveldb/blob/main/doc/table_format.md)
- [dfindexeddb Presentation](https://github.com/cclgroupltd/browser-forensics-presentation-2024)
- [dfindexeddb GitHub](https://github.com/google/dfindexeddb)
- [ccl_chromium_reader GitHub](https://github.com/cclgroupltd/ccl_chromium_reader)
