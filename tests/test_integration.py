"""
Integration tests against a real 4D SQL server.

Connection is configured via environment variables (or a repo-root .env.test
file that is gitignored).  Defaults point at the internal test server; only
the password has no default and must be supplied via env.

  FOURD_HOST    4D server hostname/IP  (default: 192.168.1.239)
  FOURD_PORT    SQL port               (default: 19812)
  FOURD_USER    SQL user               (default: sqluser)
  FOURD_PWD     SQL password           (required — no default)
  FOURD_TABLE   table used for queries (default: Patient)
  FOURD_ID_COL  integer PK column name (default: Id)

Run the suite:
  uv run --with pytest --with python-dateutil --with cffi pytest tests/test_integration.py -v

Skip when no server is reachable (runs automatically when server is down):
  The tests self-skip if the TCP port is not reachable.
"""
import os
import socket

import pytest

# ── connection config ──────────────────────────────────────────────────────────

_HOST   = os.environ.get("FOURD_HOST",  "192.168.1.239")
_PORT   = int(os.environ.get("FOURD_PORT",  "19812"))
_USER   = os.environ.get("FOURD_USER",  "sqluser")
_PWD    = os.environ.get("FOURD_PWD",   "")   # supply via .env.test or env
_TABLE  = os.environ.get("FOURD_TABLE", "Patient")
_ID_COL = os.environ.get("FOURD_ID_COL", "Id")

# ── availability guard ─────────────────────────────────────────────────────────

def _server_reachable(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


_SERVER_UP = _server_reachable(_HOST, _PORT)

pytestmark = pytest.mark.skipif(
    not _SERVER_UP,
    reason=f"4D server not reachable at {_HOST}:{_PORT}",
)


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def conn():
    """Open one connection for the whole module; close when done."""
    import p4d
    c = p4d.connect(host=_HOST, port=_PORT, user=_USER, password=_PWD, database="")
    yield c
    c.close()


# ── connection / cursor lifecycle ──────────────────────────────────────────────

class TestConnection:
    def test_connect_succeeds(self, conn):
        assert conn.connected is True

    def test_cursor_created(self, conn):
        cur = conn.cursor()
        assert cur is not None
        cur.close()

    def test_cursor_close_idempotent(self, conn):
        cur = conn.cursor()
        cur.close()
        cur.close()   # second close must not raise


# ── header-reader regression (the ba91f7d → f4bcfe7 fix) ─────────────────────
#
# The chunk-based recv in socket_receiv_header could consume body bytes that
# socket_receiv_data needed, causing the driver to hang indefinitely.
# Any SELECT that returns rows exercises the full header→body read path.

class TestHeaderReaderRegression:
    def test_select_returns_rows_without_hanging(self, conn):
        """SELECT must return at least one row promptly (no hang)."""
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        row = cur.fetchone()
        assert row is not None, f"Expected at least one row from {_TABLE}"
        cur.close()

    def test_select_with_where_clause(self, conn):
        """Parameterised WHERE clause exercises prepare→exec path."""
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > ?", [0], pagesize=5)
        rows = cur.fetchmany(5)
        assert isinstance(rows, list)
        assert len(rows) > 0
        cur.close()

    def test_multi_page_fetch(self, conn):
        """Fetch across multiple protocol pages to stress the recv loop."""
        cur = conn.cursor()
        cur.pagesize = 5
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0")
        rows = []
        while True:
            chunk = cur.fetchmany(5)
            if not chunk:
                break
            rows.extend(chunk)
            if len(rows) >= 20:   # enough to cross a page boundary
                break
        assert len(rows) > 0
        cur.close()

    def test_start_transaction_path(self, conn):
        """
        Second hang trace: fourd_exec_statement called from __start_transaction__.
        Every execute() implicitly calls __start_transaction__; verify it returns.
        """
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        assert cur.fetchone() is not None
        cur.close()

    def test_column_names_in_description(self, conn):
        """description must be populated; names are bytes (4D returns them raw)."""
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        cur.fetchone()
        assert cur.description is not None
        assert len(cur.description) > 0
        for col in cur.description:
            # 4D returns column names as bytes; callers decode them (see ingest._col_names)
            assert isinstance(col[0], (str, bytes)), f"unexpected name type: {type(col[0])}"
            assert len(col[0]) > 0
        cur.close()

    def test_second_query_on_same_cursor(self, conn):
        """Re-using a cursor for a second execute must not corrupt state."""
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        first = cur.fetchone()
        cur.execute(f"SELECT * FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        second = cur.fetchone()
        assert first is not None
        assert second is not None
        cur.close()


# ── data-type sanity ───────────────────────────────────────────────────────────

class TestDataTypes:
    def test_integer_pk_is_int(self, conn):
        cur = conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        row = cur.fetchone()
        assert row is not None
        assert isinstance(row[0], int), f"expected int, got {type(row[0])}"
        cur.close()

    def test_fetchmany_respects_count(self, conn):
        cur = conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=10)
        rows = cur.fetchmany(5)
        assert 1 <= len(rows) <= 5
        cur.close()

    def test_fetchall(self, conn):
        # NOTE: pagesize is now honoured for every FETCH-RESULT page (it used
        # to silently fall back to 100 after the first page), so a full-table
        # fetchall needs a realistic page size or it makes rows/pagesize
        # round trips.
        cur = conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=2000)
        rows = cur.fetchall()
        assert isinstance(rows, list)
        assert len(rows) > 0
        cur.close()

    def test_rowcount_populated(self, conn):
        cur = conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        # rowcount may be -1 if server didn't report it, but must not crash
        assert isinstance(cur.rowcount, int)
        cur.close()


# ── read-only mode ─────────────────────────────────────────────────────────────

class TestReadOnly:
    # The 4D server licence may only allow one concurrent SQL connection, so
    # flip the shared connection into read-only mode rather than opening a
    # second one. read_only is a plain client-side attribute.
    @pytest.fixture()
    def ro_conn(self, conn):
        conn.rollback()  # leave any implicit transaction from earlier tests
        conn.read_only = True
        yield conn
        conn.read_only = False

    def test_select_works(self, ro_conn):
        cur = ro_conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        assert cur.fetchone() is not None
        cur.close()

    def test_no_transaction_opened(self, ro_conn):
        cur = ro_conn.cursor()
        cur.execute(f"SELECT {_ID_COL} FROM {_TABLE} WHERE {_ID_COL} > 0", pagesize=1)
        cur.fetchone()
        assert ro_conn.in_transaction is False
        cur.close()

    def test_write_statement_rejected(self, ro_conn):
        from p4d.p4d import NotSupportedError
        cur = ro_conn.cursor()
        with pytest.raises(NotSupportedError):
            cur.execute(f"UPDATE {_TABLE} SET {_ID_COL} = {_ID_COL} WHERE 1 = 0")
        with pytest.raises(NotSupportedError):
            cur.execute(f"DELETE FROM {_TABLE} WHERE 1 = 0")
        with pytest.raises(NotSupportedError):
            cur.execute("INSERT INTO NoSuchTable (a) VALUES (1)")
        cur.close()


# ── error-handling ─────────────────────────────────────────────────────────────

class TestErrors:
    def test_bad_sql_raises_programming_error(self, conn):
        from p4d.p4d import ProgrammingError
        cur = conn.cursor()
        with pytest.raises(ProgrammingError):
            cur.execute("SELECT * FROM ThisTableDoesNotExist_xyz")
        cur.close()

    def test_closed_cursor_raises_interface_error(self, conn):
        from p4d.p4d import InterfaceError
        cur = conn.cursor()
        cur.close()
        with pytest.raises(InterfaceError):
            cur.execute(f"SELECT {_ID_COL} FROM {_TABLE}")
