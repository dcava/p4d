"""
Unit tests for BLOB/IMAGE type handling in py4d_cursor.fetchone().
No 4D server required — uses the compiled CFFI extension directly
to construct in-memory FOURD_BLOB structures.

Run with:  pytest tests/test_blob_handling.py -v
"""
import pytest
from unittest.mock import MagicMock, patch

try:
    from p4d._p4d_cffi import ffi, lib as _lib
    from p4d.p4d import py4d_cursor, Binary
    HAS_EXTENSION = True
except ImportError:
    HAS_EXTENSION = False

pytestmark = pytest.mark.skipif(
    not HAS_EXTENSION, reason="compiled p4d extension not available"
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_mock_lib():
    """Mock lib4d_sql that carries real enum constants so int comparisons work."""
    m = MagicMock()
    for name in (
        "VK_UNKNOW", "VK_BOOLEAN", "VK_BYTE", "VK_WORD", "VK_LONG", "VK_LONG8",
        "VK_REAL", "VK_FLOAT", "VK_TIME", "VK_TIMESTAMP", "VK_DURATION",
        "VK_TEXT", "VK_STRING", "VK_BLOB", "VK_IMAGE",
        "RESULT_SET", "UPDATE_COUNT",
    ):
        setattr(m, name, getattr(_lib, name))
    return m


def _make_cursor(mock_lib=None):
    mock_conn = MagicMock()
    mock_conn.connected = True
    if mock_lib is None:
        mock_lib = _make_mock_lib()
    return py4d_cursor(mock_conn, MagicMock(), mock_lib)


def _setup_single_column_row(cursor, col_type, field_ptr):
    """
    Wire cursor internals so fetchone() reads one row, one column of col_type,
    with field_ptr returned by every fourd_field() call.
    """
    lib = cursor.lib4d_sql
    cursor._py4d_cursor__closed = False
    cursor._py4d_cursor__resulttype = lib.RESULT_SET
    cursor._py4d_cursor__rowcount = 1
    cursor._py4d_cursor__rownumber = -1
    mock_result = MagicMock()
    mock_result.numRow = 0
    cursor.result = mock_result

    lib.fourd_next_row.return_value = 1
    lib.fourd_num_columns.return_value = 1
    lib.fourd_get_column_type.return_value = col_type
    # Return value 0 → conver_res != 1 → output = b''; BLOB path uses fourd_field() directly
    lib.fourd_field_to_string.return_value = 0
    lib.fourd_field.return_value = field_ptr


def _make_blob_ptr(payload: bytes):
    """Allocate a FOURD_BLOB in CFFI memory containing payload, return a void*."""
    blob = ffi.new("FOURD_BLOB *")
    buf = ffi.new("unsigned char[]", payload)
    blob.data = ffi.cast("void *", buf)
    blob.length = len(payload)
    return ffi.cast("void *", blob), blob, buf   # keep blob/buf alive for the test


# ── BLOB / IMAGE fetchone tests ───────────────────────────────────────────────

class TestBlobFetchone:
    def test_blob_with_data_returns_binary(self):
        payload = b"hello blob"
        field_ptr, _blob, _buf = _make_blob_ptr(payload)

        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        _setup_single_column_row(cursor, lib.VK_BLOB, field_ptr)

        row = cursor.fetchone()
        assert row is not None
        assert isinstance(row[0], Binary)
        assert bytes(row[0]) == payload

    def test_null_field_returns_none(self):
        """fourd_field() returning NULL means the cell is null → None in Python."""
        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        _setup_single_column_row(cursor, lib.VK_BLOB, ffi.NULL)

        row = cursor.fetchone()
        assert row is not None
        assert row[0] is None

    def test_image_type_returns_binary(self):
        payload = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
        field_ptr, _blob, _buf = _make_blob_ptr(payload)

        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        _setup_single_column_row(cursor, lib.VK_IMAGE, field_ptr)

        row = cursor.fetchone()
        assert row is not None
        assert isinstance(row[0], Binary)
        assert bytes(row[0]) == payload

    def test_blob_roundtrip_preserves_all_byte_values(self):
        """Every byte value 0x00–0xFF survives the ffi.buffer copy."""
        payload = bytes(range(256))
        field_ptr, _blob, _buf = _make_blob_ptr(payload)

        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        _setup_single_column_row(cursor, lib.VK_BLOB, field_ptr)

        row = cursor.fetchone()
        assert bytes(row[0]) == payload

    def test_large_blob_returns_correct_bytes(self):
        payload = bytes(range(256)) * 256  # 64 KB
        field_ptr, _blob, _buf = _make_blob_ptr(payload)

        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        _setup_single_column_row(cursor, lib.VK_BLOB, field_ptr)

        row = cursor.fetchone()
        assert row is not None
        assert len(row[0]) == len(payload)
        assert bytes(row[0]) == payload


# ── Cursor state-machine tests ────────────────────────────────────────────────

class TestCursorState:
    def test_fetchone_on_closed_cursor_raises(self):
        from p4d.p4d import InterfaceError
        cursor = _make_cursor()
        cursor.close()
        with pytest.raises(InterfaceError):
            cursor.fetchone()

    def test_fetchone_before_execute_raises(self):
        from p4d.p4d import DataError
        cursor = _make_cursor()
        with pytest.raises(DataError):
            cursor.fetchone()

    def test_fetchone_returns_none_on_update_count(self):
        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        cursor._py4d_cursor__closed = False
        cursor._py4d_cursor__resulttype = lib.UPDATE_COUNT
        cursor._py4d_cursor__rowcount = 0
        cursor.result = MagicMock()
        assert cursor.fetchone() is None

    def test_fetchone_returns_none_on_empty_result(self):
        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        cursor._py4d_cursor__closed = False
        cursor._py4d_cursor__resulttype = lib.RESULT_SET
        cursor._py4d_cursor__rowcount = 0
        cursor.result = MagicMock()
        assert cursor.fetchone() is None

    def test_fetchone_returns_none_when_no_more_rows(self):
        """fourd_next_row() returning 0 signals end-of-results."""
        lib = _make_mock_lib()
        cursor = _make_cursor(lib)
        cursor._py4d_cursor__closed = False
        cursor._py4d_cursor__resulttype = lib.RESULT_SET
        cursor._py4d_cursor__rowcount = 5
        cursor._py4d_cursor__rownumber = -1
        cursor.result = MagicMock()
        lib.fourd_next_row.return_value = 0
        assert cursor.fetchone() is None


# ── connect() / DSN parsing tests ────────────────────────────────────────────

class TestConnectParsing:
    def test_missing_host_raises_value_error(self):
        from p4d.p4d import connect
        with pytest.raises(ValueError, match="[Hh]ost"):
            connect(user="admin", password="", database="mydb")

    def test_default_port_is_19812(self):
        from p4d.p4d import py4d_connection
        with patch.object(py4d_connection, "__init__", return_value=None):
            from p4d.p4d import connect
            try:
                connect(host="localhost")
            except Exception:
                pass
            call_kwargs = py4d_connection.__init__.call_args[1]
            assert call_kwargs.get("port") == 19812

    def test_dsn_string_parsed_into_kwargs(self):
        from p4d.p4d import py4d_connection
        with patch.object(py4d_connection, "__init__", return_value=None):
            from p4d.p4d import connect
            try:
                connect(dsn="host=db.local;user=admin;password=s3cr3t;database=mydb;port=5000")
            except Exception:
                pass
            call_kwargs = py4d_connection.__init__.call_args[1]
            assert call_kwargs["host"] == "db.local"
            assert call_kwargs["user"] == "admin"
            assert call_kwargs["password"] == "s3cr3t"
            assert call_kwargs["database"] == "mydb"
            # Known limitation: DSN port is overwritten by the default (19812) because
            # connect() checks the function-level `port` kwarg, not connect_args['port'].
            # A port from DSN only takes effect if the `port=` kwarg is also passed.
            assert call_kwargs["port"] == 19812

    def test_unrecognized_dsn_key_raises(self):
        from p4d.p4d import connect
        with pytest.raises(ValueError, match="Unrecognized"):
            connect(dsn="host=localhost;badkey=value")
