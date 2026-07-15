# p4d

A Python [DB API 2.0](https://peps.python.org/pep-0249/) compliant driver for the [4D](https://www.4d.com) database server.

Built on top of 4D's `lib4d_sql` C library and integrated into Python via [CFFI](https://cffi.readthedocs.io/).

This is an actively maintained fork of [ibrewster/p4d](https://github.com/ibrewster/p4d), which is no longer maintained.

---

## You probably don't want to use this....

This library facilitates access to a 4D database via the exposed SQL backend. 4D speaks an SQL dialect that is not well documented. I updated this fork to support BLOBs which are new since the lib_4dsql library was first released by 4D. Since that time, 4D have discontinued ODBC drivers for MacOS (last v18) and Windows (v20). Windows ODBC drivers do continue to work with 4Dv21 and that pathway should be strongly preferred over this library. If you don't have a Windows PC or a working ODBC driver, then p4d will get the job done.

Please don't write anything important that relies on this library.
---

---


## Installation

**From GitHub (recommended):**

```sh
pip install git+https://github.com/dcava/p4d.git
# or
uv pip install git+https://github.com/dcava/p4d.git
```

**Requirements:** A C compiler, `cffi`, and `python-dateutil` (installed automatically). On macOS, Xcode command-line tools suffice (`xcode-select --install`).

---

## Quick start

```python
import p4d

conn = p4d.connect(host="192.168.1.1", user="sqluser", password="secret", database="", port=19812)

cur = conn.cursor()
cur.execute("SELECT Id, Name FROM MyTable WHERE Id > :id", {"id": 100})
for row in cur.fetchall():
    print(row)

conn.close()
```

Connection parameters follow the DB API 2.0 convention. You can also use a DSN string:

```python
conn = p4d.connect(dsn="host=192.168.1.1;user=sqluser;password=secret;port=19812")
```

Use as a context manager:

```python
with p4d.connect(...) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM MyTable")
        rows = cur.fetchmany(500)
```

### Parameter styles

All three common styles are supported:

```python
cur.execute("SELECT * FROM T WHERE Id = %s", [42])           # format
cur.execute("SELECT * FROM T WHERE Id = %(id)s", {"id": 42}) # pyformat
cur.execute("SELECT * FROM T WHERE Id = :id", {"id": 42})    # named
```

### Read-only connections

For analytics/reporting workloads, open the connection read-only:

```python
conn = p4d.connect(host="...", user="...", password="...", read_only=True)
```

A read-only connection never opens implicit transactions (saving a round
trip on the first query) and raises `NotSupportedError` for any statement
that is not a `SELECT`, so it cannot hold write locks on the server.

### Pagination

Rows are fetched from the server in pages. The default page size is 1000
rows; tune it per connection or per query:

```python
conn = p4d.connect(host="...", pagesize=5000)          # connection default
cur.execute("SELECT * FROM BigTable", pagesize=5000)   # per query
```

Larger pages mean fewer server round trips (each FETCH-RESULT round trip
has substantial fixed cost on the 4D server) at the cost of more client
memory per page. As of v2.2 the page size is honoured for *every* page,
not just the first; keep it modest for tables with large BLOB columns.

```python
cur = conn.cursor()
cur.pagesize = 5000
cur.execute("SELECT * FROM BigTable")
while True:
    rows = cur.fetchmany(1000)
    if not rows:
        break
    process(rows)
```

---

## Testing

The test suite includes unit tests for BLOB handling and cursor state (no server needed)
and integration tests against a live 4D server.

**Unit tests (no server required):**

```sh
pytest tests/test_blob_handling.py -v
```

**Integration tests (requires a 4D server):**

Create a gitignored `.env.test` file at the repo root:

```
FOURD_HOST=your-server-ip
FOURD_PORT=19812
FOURD_USER=sqluser
FOURD_PWD=your-password
FOURD_TABLE=Patient
FOURD_ID_COL=Id
```

Then run:

```sh
pytest tests/test_integration.py -v
```

Tests auto-skip if the server is unreachable. The table needs at least one
row with an integer primary key.

---

## Environment

| Variable | Default | Purpose |
|---|---|---|
| *(none)* | — | All config is passed to `p4d.connect()` directly |

---

## License

The Python driver (`p4d/`) is released under the **MIT License** — see [LICENSE](LICENSE).

The bundled `lib4d_sql` C library is copyright © 2009 4D SAS, offered under your choice of PHP 3.0.1, Apache 2.0, LGPL 3.0, GPL 3.0, or BSD. This project uses it under the **BSD** licence.

---

## Changelog

### v2.2 (2026-07)

Performance and robustness overhaul of the wire protocol layer and fetch path.
Measured against a real 4D server over a WireGuard link (5,000 rows × 136
columns): fetch throughput went from ~350 to ~1,900 rows/s and the
integration suite from 25s to 4s.

**Performance**
- `lib4d_sql`: new 64 KB buffered socket reader. Headers and row data were
  previously read with one `recv()` syscall per byte/field (millions of
  syscalls for large result sets); reads now come out of a buffer refilled
  in bulk, and large BLOB/string bodies are received directly into their
  destination.
- `lib4d_sql`: per-result arena allocator. Cell values were individually
  `calloc`'d and `free`'d (one pair per cell); they are now bump-allocated
  from 256 KB arena chunks and freed in one pass with the result.
- `cursor.pagesize` is now honoured for every FETCH-RESULT page (previously
  hardcoded to 100 rows after the first page), and the default page size is
  1000. `connect(pagesize=...)` sets the connection-wide default.
- Python fetch path: column types are cached once per execute; each cell is
  decoded with a single FFI call and a direct typed cast. The old path
  converted every cell to a C string first (even integers) and made ~6 FFI
  calls per cell.
- `connect(read_only=True)` skips implicit `START TRANSACTION` (one less
  round trip on first query).

**Robustness**
- Every socket read/write is now checked; a connection drop mid-result
  raises `OperationalError` instead of silently returning truncated rows.
- Wire-format validation: string/BLOB/FLOAT lengths are bounds-checked with
  overflow-safe arithmetic (a corrupt length previously drove a negative
  `calloc` and crashed); unknown column types abort cleanly instead of
  desynchronising the stream; `Column-Count` and row counts are validated.
- `read_only=True` rejects non-SELECT statements with `NotSupportedError`.
- Fixed inverted boolean in `fourd_field_to_string`.
- Fixed `fourd_field_long` misuse for 2-byte WORD/BYTE columns (read 4 bytes
  from a 2-byte allocation) and 8-byte DURATION columns (read only 4 bytes).
- Fixed `None` query parameters being sent as the string `"None"` instead
  of SQL NULL.
- Fixed memory leaks: response header + column metadata leaked on every
  FETCH-RESULT page; several error paths leaked the result set.
- `executemany()` no longer crashes when describing a freed result.

### v2.1 (2026-06)

**Python driver:**
- Fix `%%` escape in format-style queries (was silently ignored, passed `%%` to server)
- Fix DSN-provided port being overwritten by default 19812
- Fix double-free risk when cursor used as context manager (`__exit__` now sets `fourd_query = None`)
- Fix statement leak on cursor re-execute (old statement now freed before preparing new one)
- Fix `executemany` flow: close and free results correctly between batches
- Fix null float/double columns appending both `None` and `float()` to the row
- Remove Python 2 compatibility shims (package requires Python ≥ 3.8)
- Fix `setinputsizes`/`setoutputsize` signatures to match DB API 2.0
- Replace mutable default argument (`params=[]`) with `params=None`
- Use library-provided `Free()` instead of bare `free()` for C allocations

**C library (lib4d_sql):**
- Fix memory leak in `fourd_free_statement`: parameter value copies are now freed
- Fix memory leak in `_free_data_result`: `VK_IMAGE` fields now freed via `FreeBlob`
- Expose `Free()` in public API so callers can free library-allocated memory

**Tests:**
- Fix DSN parsing test to assert new correct behavior (port preserved from DSN)

### v2.0 (2026)
*Fork relaunched as dcava/p4d — upstream (ibrewster/p4d) is no longer maintained.*

- Add README.md, MIT licence, and proper GitHub packaging
- Fix `VK_BLOB_OBJ` column handling; harden datetime and BLOB parsing
- Handle `VK_UNKNOWN` (type 0) gracefully in cursor description
- Modernise CFFI setup: replace deprecated `verifier` with out-of-line API mode
- Fix `fetchmany` `NameError` (`none` → `None`)
- Fix socket header-reader hang (chunked `recv` consumed body bytes, now reads byte-at-a-time)

### v1.9 (2023-01-13) — ibrewster/p4d
- Fix datatype in C library to properly handle characters > 128

### v1.8
- Handle decoding of strings from 4D when the string contains corrupted data
- Change `Binary` data type to subclass of `bytes` rather than `str`

### v1.6.1
- Fix potential issue where memory is freed too soon

### v1.6
- Don't close the connection when calling `close()` on a cursor
- Fix some potential buffer overflows with many-column queries

### v1.5
- Explicitly set `cursor.result` to `None` when closing connection to avoid possible double-free

### v1.4
- Add port number as optional parameter to `connect()`
- Fix includes in C code needed for proper compilation on newer OS versions

### v1.3
- Properly decode integer result fields on Python 3

### v1.2
- Fix bug that could corrupt strings during insert/update with long strings

### v1.1
- Fix bug where inability to prepare a query prevented it from running at all

### v1.0
- Enable cursor/connection to work as context managers
- Wrap all queries in a transaction block

### v0.9
- Fix bug calling `.decode()` on a `str` in Python 3
- Add support for `pyformat`, `format`, and `named` parameter styles

### v0.8
- Python 3 compatibility

### v0.7
- Fix bug with running multiple queries in a row on the same cursor

### v0.6
- Fix bug with time values containing milliseconds

### v0.5.1
- Improved method of freeing memory used by `fetchone`

### v0.5
- Fix remaining memory leak with `executemany`

### v0.4
- Fix memory leak in `executemany`
- Fix performance issue with large `executemany` queries

### v0.3
- Improve performance when receiving large datasets containing date/time values
- Close statement after execution when doing insert many

### v0.2
- Fix lib4d_sql paging bug
- Fix lib4d_sql long query/argument string bug
- Fix lib4d_sql query preparation bug

### v0.1.1
- Initial release
