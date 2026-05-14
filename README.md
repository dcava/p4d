# p4d

A Python [DB API 2.0](https://peps.python.org/pep-0249/) compliant driver for the [4D](https://www.4d.com) database server.

Built on top of 4D's `lib4d_sql` C library and integrated into Python via [CFFI](https://cffi.readthedocs.io/).

This is an actively maintained fork of [ibrewster/p4d](https://github.com/ibrewster/p4d), which is no longer maintained.

---

## You probably don't want to use this....

This library facilitates access to a 4D database via the exposed SQL backend. 4D speaks an SQL dialect that is not well documented. I updated this fork to support BLOBs which are new since the lib_4dsql library was first released by 4D. Since that time, 4D have discontinued ODBC drivers for MacOS (last v18) and Windows (v20). Windows ODBC drivers do continue to work with 4Dv21 and that pathway should be strongly prefered over this library. If you don't have a Windows PC or a working ODBC driver, then p4d will get the job done.

Please don't write anything important that relies on this library.

---


## Installation

**From GitHub (recommended):**

```sh
pip install git+https://github.com/dcava/p4d.git
# or
uv pip install git+https://github.com/dcava/p4d.git
```

**Requirements:** A C compiler and `cffi` (installed automatically). On macOS, Xcode command-line tools suffice (`xcode-select --install`).

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

Connection parameters follow the DB API 2.0 convention. Use as a context manager:

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

### Pagination

For large result sets, set `cursor.pagesize` before executing:

```python
cur = conn.cursor()
cur.pagesize = 1000
cur.execute("SELECT * FROM BigTable")
while True:
    rows = cur.fetchmany(1000)
    if not rows:
        break
    process(rows)
```

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

### v2.0 (2026)
*Fork relaunched as dcava/p4d — upstream (ibrewster/p4d) is no longer maintained.*

- Add README.md, MIT licence, and proper GitHub packaging
- Fix `VK_BLOB_OBJ` column handling; harden datetime and BLOB parsing
- Handle `VK_UNKNOWN` (type 0) gracefully in cursor description
- Modernise CFFI setup: replace deprecated `verifier` with out-of-line API mode
- Fix `fetchmany` `NameError` (`none` → `None`)
- Communications layer updates

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
