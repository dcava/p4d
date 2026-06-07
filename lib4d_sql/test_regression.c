/*
  +----------------------------------------------------------------------+
  | lib4D_SQL — Regression tests                                         |
  +----------------------------------------------------------------------+
  | Covers bugs fixed in the fix/lib4d_sql-bugs-and-modernise branch     |
  +----------------------------------------------------------------------+
*/
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "fourd.h"
#include "fourd_int.h"
#include "base64.h"
#include "utils.h"

static int tests_run = 0;
static int tests_failed = 0;

#define TEST(name) do { tests_run++; printf("  %-50s", name); } while(0)
#define PASS()       printf("PASS\n")
#define FAIL(fmt,...) do { \
    tests_failed++; \
    printf("FAIL — " fmt "\n", ##__VA_ARGS__); \
} while(0)
#define CHECK(cond, fmt,...) do { \
    if (!(cond)) { FAIL(fmt, ##__VA_ARGS__); return; } \
} while(0)

/* ── base64 round-trip ─────────────────────────────────────────────── */

static void test_base64_roundtrip(void)
{
    TEST("base64 round-trip ASCII");
    const char *input = "Hello, World!";
    int enclen, declen;
    unsigned char *enc = base64_encode(input, strlen(input), &enclen);
    CHECK(enc != NULL, "encode returned NULL");
    unsigned char *dec = base64_decode((const char*)enc, enclen, &declen);
    CHECK(dec != NULL, "decode returned NULL");
    CHECK(declen == (int)strlen(input), "length mismatch: %d != %zu", declen, strlen(input));
    CHECK(memcmp(dec, input, declen) == 0, "content mismatch");
    free(enc);
    free(dec);
    PASS();
}

static void test_base64_high_bytes(void)
{
    TEST("base64 high bytes (signed char bug)");
    /* bytes >= 0x80 triggered negative array index in base64_reverse_table */
    unsigned char input[] = { 0x00, 0x7F, 0x80, 0xFF, 0x42, 0x00 };
    int enclen, declen;
    unsigned char *enc = base64_encode((const char*)input, sizeof(input), &enclen);
    CHECK(enc != NULL, "encode returned NULL");
    unsigned char *dec = base64_decode((const char*)enc, enclen, &declen);
    CHECK(dec != NULL, "decode returned NULL (high bytes likely caused signed-char OOB)");
    CHECK(declen == (int)sizeof(input), "length mismatch: %d != %zu", declen, sizeof(input));
    CHECK(memcmp(dec, input, sizeof(input)) == 0, "content mismatch for high bytes");
    free(enc);
    free(dec);
    PASS();
}

static void test_base64_decode_handles_high_bytes(void)
{
    TEST("base64_decode handles bytes >= 0x80 safely");
    /* non-strict mode skips all invalid characters (ch < 0 in table).
       The fix for the signed-char bug means bytes >= 0x80 no longer
       cause an out-of-bounds array read.  Instead they're skipped or
       rejected cleanly.  This test just verifies no crash occurs. */
    int declen;
    unsigned char *dec = base64_decode("\x80\x80\x80\x80", 4, &declen);
    /* non-strict: all bytes skipped → empty output */
    CHECK(dec != NULL, "unexpected NULL from non-strict decode");
    CHECK(declen == 0, "expected length 0, got %d", declen);
    free(dec);
    PASS();
}

/* ── strstrip ──────────────────────────────────────────────────────── */

static void test_strstrip_spaces(void)
{
    TEST("strstrip leading/trailing spaces");
    char s[] = "  hello  ";
    char *r = strstrip(s);
    CHECK(strcmp(r, "hello") == 0, "got '%s'", r);
    PASS();
}

static void test_strstrip_tabs(void)
{
    TEST("strstrip tabs and newlines");
    char s[] = "\t\nmiddle\r\n";
    char *r = strstrip(s);
    CHECK(strcmp(r, "middle") == 0, "got '%s'", r);
    PASS();
}

static void test_strstrip_empty(void)
{
    TEST("strstrip empty string");
    char s[] = "";
    char *r = strstrip(s);
    CHECK(strcmp(r, "") == 0, "got '%s'", r);
    PASS();
}

static void test_strstrip_all_whitespace(void)
{
    TEST("strstrip all whitespace");
    char s[] = "   \t  ";
    char *r = strstrip(s);
    CHECK(strcmp(r, "") == 0, "got '%s'", r);
    PASS();
}

/* ── typeFromString / stringFromType ───────────────────────────────── */

static void test_type_roundtrip(void)
{
    TEST("typeFromString <-> stringFromType");
    const char *types[] = {
        "VK_BOOLEAN", "VK_BYTE", "VK_WORD", "VK_LONG", "VK_LONG8",
        "VK_REAL", "VK_FLOAT", "VK_TIMESTAMP", "VK_TIME",
        "VK_DURATION", "VK_TEXT", "VK_STRING", "VK_BLOB_OBJ",
        "VK_BLOB", "VK_IMAGE", NULL
    };
    for (int i = 0; types[i]; i++) {
        FOURD_TYPE t = typeFromString(types[i]);
        CHECK(t != VK_UNKNOW, "typeFromString('%s') returned UNKNOW", types[i]);
        const char *s = stringFromType(t);
        CHECK(s != NULL, "stringFromType returned NULL for %d", t);
        /* Some types map to the same enum (VK_TEXT->VK_STRING, VK_TIME->VK_TIMESTAMP, VK_BLOB_OBJ->VK_BLOB) */
    }
    PASS();
}

static void test_typeFromString_unknown(void)
{
    TEST("typeFromString returns UNKNOW for garbage");
    FOURD_TYPE t = typeFromString("NOT_A_TYPE");
    CHECK(t == VK_UNKNOW, "expected VK_UNKNOW, got %d", t);
    PASS();
}

/* ── vk_sizeof ────────────────────────────────────────────────────── */

static void test_vk_sizeof(void)
{
    TEST("vk_sizeof returns correct sizes");
    CHECK(vk_sizeof(VK_BOOLEAN)   == 2,    "VK_BOOLEAN: %d", vk_sizeof(VK_BOOLEAN));
    CHECK(vk_sizeof(VK_BYTE)      == 2,    "VK_BYTE: %d", vk_sizeof(VK_BYTE));
    CHECK(vk_sizeof(VK_WORD)      == 2,    "VK_WORD: %d", vk_sizeof(VK_WORD));
    CHECK(vk_sizeof(VK_LONG)      == 4,    "VK_LONG: %d", vk_sizeof(VK_LONG));
    CHECK(vk_sizeof(VK_LONG8)     == 8,    "VK_LONG8: %d", vk_sizeof(VK_LONG8));
    CHECK(vk_sizeof(VK_REAL)      == 8,    "VK_REAL: %d", vk_sizeof(VK_REAL));
    CHECK(vk_sizeof(VK_DURATION)  == 8,    "VK_DURATION: %d", vk_sizeof(VK_DURATION));
    CHECK(vk_sizeof(VK_FLOAT)     == -1,   "VK_FLOAT: %d", vk_sizeof(VK_FLOAT));
    CHECK(vk_sizeof(VK_TIME)      == 8,    "VK_TIME: %d", vk_sizeof(VK_TIME));
    CHECK(vk_sizeof(VK_TIMESTAMP) == 8,    "VK_TIMESTAMP: %d", vk_sizeof(VK_TIMESTAMP));
    CHECK(vk_sizeof(VK_STRING)    == -1,   "VK_STRING: %d", vk_sizeof(VK_STRING));
    CHECK(vk_sizeof(VK_BLOB)      == -1,   "VK_BLOB: %d", vk_sizeof(VK_BLOB));
    CHECK(vk_sizeof(VK_IMAGE)     == -1,   "VK_IMAGE: %d", vk_sizeof(VK_IMAGE));
    CHECK(vk_sizeof(VK_UNKNOW)    == 0,    "VK_UNKNOW: %d", vk_sizeof(VK_UNKNOW));
    PASS();
}

/* ── _get_status ──────────────────────────────────────────────────── */

static void test_get_status_OK(void)
{
    TEST("_get_status OK header");
    const char *header = "001 OK\r\nStatement-ID:42\r\n\r\n";
    int status = -1;
    FOURD_LONG8 error_code = -1;
    char error_string[256];
    FOURD_LONG8 ret = _get_status(header, &status, &error_code, error_string);
    CHECK(ret == 0, "expected 0, got %lld", (long long)ret);
    CHECK(status == FOURD_OK, "expected FOURD_OK (0), got %d", status);
    CHECK(error_code == 0, "expected error_code 0, got %lld", (long long)error_code);
    CHECK(error_string[0] == 0, "expected empty error_string");
    PASS();
}

static void test_get_status_error(void)
{
    TEST("_get_status error header");
    const char *header = "042 ERROR\r\nError-Code:1101\r\n"
                         "Error-Description:Table does not exist\r\n\r\n";
    int status = -1;
    FOURD_LONG8 error_code = 0;
    char error_string[ERROR_STRING_LENGTH] = {0};
    FOURD_LONG8 ret = _get_status(header, &status, &error_code, error_string);
    CHECK(ret == 1101, "expected 1101, got %lld", (long long)ret);
    CHECK(status == FOURD_ERROR, "expected FOURD_ERROR (1), got %d", status);
    CHECK(error_code == 1101, "expected error_code 1101, got %lld", (long long)error_code);
    CHECK(strcmp(error_string, "Table does not exist") == 0,
          "got error_string '%s'", error_string);
    PASS();
}

/* ── get() — header field extraction ──────────────────────────────── */

static void test_get_plain_field(void)
{
    TEST("get() plain field");
    const char *header = "Column-Count:5\r\nFoo:bar\r\n\r\n";
    char value[256];
    int ret = get(header, "Column-Count", value, sizeof(value));
    CHECK(ret == 0, "get returned %d", ret);
    CHECK(strcmp(value, "5") == 0, "got '%s'", value);
    PASS();
}

static void test_get_base64_field(void)
{
    TEST("get() base64 field");
    /* base64("hello") = "aGVsbG8=" */
    const char *header = "Column-Aliases-Base64:aGVsbG8=\r\n\r\n";
    char value[256];
    int ret = get(header, "Column-Aliases-Base64", value, sizeof(value));
    CHECK(ret == 0, "get returned %d", ret);
    CHECK(strcmp(value, "hello") == 0, "got '%s'", value);
    PASS();
}

static void test_get_missing_section(void)
{
    TEST("get() missing section");
    const char *header = "Foo:bar\r\n\r\n";
    char value[256];
    int ret = get(header, "Not-There", value, sizeof(value));
    CHECK(ret == -1, "expected -1, got %d", ret);
    PASS();
}

/* ── _is_multi_query ──────────────────────────────────────────────── */

static void test_is_multi_query_single(void)
{
    TEST("_is_multi_query: single statement");
    CHECK(_is_multi_query("SELECT * FROM t") == 0, "single statement flagged as multi");
    CHECK(_is_multi_query("SELECT * FROM [Table]") == 0, "bracketed table flagged as multi");
    CHECK(_is_multi_query("SELECT ';' FROM t") == 0, "quoted semicolon flagged as multi");
    CHECK(_is_multi_query(NULL) == 0, "NULL flagged as multi");
    CHECK(_is_multi_query("") == 0, "empty string flagged as multi");
    PASS();
}

static void test_is_multi_query_multi(void)
{
    TEST("_is_multi_query: multi statement");
    CHECK(_is_multi_query("SELECT 1; SELECT 2") == 1, "multi not detected");
    CHECK(_is_multi_query("SELECT 1; \n SELECT 2") == 1, "multi not detected");
    /* semicolon inside bracket should not count */
    CHECK(_is_multi_query("SELECT [a;b] FROM t") == 0,
          "bracketed semicolon incorrectly flagged as multi");
    PASS();
}

/* ── _serialize TIMESTAMP fields ──────────────────────────────────── */

static void test_serialize_timestamp_fields(void)
{
    TEST("_serialize TIMESTAMP: year/mounth/day/milli");
    FOURD_TIMESTAMP ts = { 2024, 6, 15, 43200000 };  /* 2024-06-15 12:00:00.000 */
    unsigned int size = 0;
    char *data = _serialize(NULL, &size, VK_TIMESTAMP, &ts);
    CHECK(data != NULL, "serialize returned NULL");
    CHECK(size == 8, "expected size 8, got %u", size);

    /* Verify field order: year(2) mounth(1) day(1) milli(4) = 8 bytes */
    int16_t year;
    uint8_t mounth, day;
    uint32_t milli;
    memcpy(&year,   data + 0, 2);
    memcpy(&mounth, data + 2, 1);
    memcpy(&day,    data + 3, 1);
    memcpy(&milli,  data + 4, 4);

    CHECK(year   == 2024,       "year: %d", year);
    CHECK(mounth == 6,          "mounth: %d", mounth);
    CHECK(day    == 15,         "day: %d", day);
    CHECK(milli  == 43200000,   "milli: %u", milli);

    free(data);
    PASS();
}

/* ── _serialize BLOB (no *2 over-read) ────────────────────────────── */

static void test_serialize_blob_length(void)
{
    TEST("_serialize BLOB: correct byte length");
    unsigned char blobdata[] = { 0xAA, 0xBB, 0xCC, 0xDD, 0xEE };
    FOURD_BLOB blob = { 5, blobdata };
    unsigned int size = 0;
    char *data = _serialize(NULL, &size, VK_BLOB, &blob);
    CHECK(data != NULL, "serialize returned NULL");
    /* length(4) + data(5) = 9, NOT 4+5*2=14 */
    CHECK(size == 9, "expected size 9, got %u (old bug doubled data length)", size);

    int32_t stored_len;
    memcpy(&stored_len, data, 4);
    CHECK(stored_len == 5, "stored length: %d", stored_len);

    CHECK(memcmp(data+4, blobdata, 5) == 0, "blob data mismatch");
    free(data);
    PASS();
}

/* ── _copy round-trip ─────────────────────────────────────────────── */

static void test_copy_string(void)
{
    TEST("_copy STRING round-trip");
    unsigned char strdata[] = { 'H',0,'i',0 };  /* UTF-16LE "Hi" */
    FOURD_STRING src = { 2, strdata };
    FOURD_STRING *cp = (FOURD_STRING *)_copy(VK_STRING, &src);
    CHECK(cp != NULL, "_copy returned NULL");
    CHECK(cp->length == 2, "length: %d", cp->length);
    CHECK(memcmp(cp->data, strdata, 4) == 0, "data mismatch");
    FreeString(cp);
    PASS();
}

static void test_copy_long(void)
{
    TEST("_copy LONG value");
    FOURD_LONG val = 42;
    FOURD_LONG *cp = (FOURD_LONG *)_copy(VK_LONG, &val);
    CHECK(cp != NULL, "_copy returned NULL");
    CHECK(*cp == 42, "value: %d", *cp);
    Free(cp);
    PASS();
}

/* ── runner ───────────────────────────────────────────────────────── */

int main(void)
{
    printf("lib4d_sql regression tests\n");
    printf("==========================\n\n");

    test_base64_roundtrip();
    test_base64_high_bytes();
    test_base64_decode_handles_high_bytes();

    test_strstrip_spaces();
    test_strstrip_tabs();
    test_strstrip_empty();
    test_strstrip_all_whitespace();

    test_type_roundtrip();
    test_typeFromString_unknown();

    test_vk_sizeof();

    test_get_status_OK();
    test_get_status_error();

    test_get_plain_field();
    test_get_base64_field();
    test_get_missing_section();

    test_is_multi_query_single();
    test_is_multi_query_multi();

    test_serialize_timestamp_fields();
    test_serialize_blob_length();

    test_copy_string();
    test_copy_long();

    printf("\n==========================\n");
    printf("%d tests run, %d failed\n", tests_run, tests_failed);
    return (tests_failed == 0) ? 0 : 1;
}
