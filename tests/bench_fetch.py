"""
Fetch-path benchmark against a live 4D server.

Times fetching up to BENCH_ROWS rows from FOURD_TABLE at several page sizes,
plus a small-query latency loop. Uses the same env/.env.test configuration
as the integration tests.

Run:
    python tests/bench_fetch.py
"""
import os
import sys
import time
from pathlib import Path

# Reuse the .env.test loader from conftest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import conftest  # noqa: F401  (loads .env.test on import)

import p4d

HOST = os.environ.get("FOURD_HOST", "192.168.1.239")
PORT = int(os.environ.get("FOURD_PORT", "19812"))
USER = os.environ.get("FOURD_USER", "sqluser")
PWD = os.environ.get("FOURD_PWD", "")
TABLE = os.environ.get("FOURD_TABLE", "Patient")
ID_COL = os.environ.get("FOURD_ID_COL", "Id")
BENCH_ROWS = int(os.environ.get("BENCH_ROWS", "5000"))
PAGESIZES = [int(s) for s in os.environ.get("BENCH_PAGESIZES", "100,1000,5000").split(",")]


def bench_fetch(conn, pagesize, nrows):
    cur = conn.cursor()
    t0 = time.perf_counter()
    cur.execute(f"SELECT * FROM {TABLE} WHERE {ID_COL} > 0", pagesize=pagesize)
    t_exec = time.perf_counter() - t0
    t0 = time.perf_counter()
    got = len(cur.fetchmany(nrows))
    t_fetch = time.perf_counter() - t0
    ncols = len(cur.description)
    cur.close()
    return t_exec, t_fetch, got, ncols


def bench_small_queries(conn, n=20):
    cur = conn.cursor()
    t0 = time.perf_counter()
    for _ in range(n):
        cur.execute(f"SELECT {ID_COL} FROM {TABLE} WHERE {ID_COL} > 0", pagesize=1)
        cur.fetchone()
    elapsed = time.perf_counter() - t0
    cur.close()
    return elapsed / n


def main():
    kwargs = {}
    if os.environ.get("BENCH_READ_ONLY"):
        kwargs["read_only"] = True
    conn = p4d.connect(host=HOST, port=PORT, user=USER, password=PWD,
                       database="", **kwargs)
    print(f"server={HOST}:{PORT} table={TABLE} target_rows={BENCH_ROWS} "
          f"read_only={bool(kwargs)}")

    for ps in PAGESIZES:
        t_exec, t_fetch, got, ncols = bench_fetch(conn, ps, BENCH_ROWS)
        total = t_exec + t_fetch
        rate = got / total if total > 0 else float("inf")
        print(f"pagesize={ps:>6}  rows={got:>6} cols={ncols:>3}  "
              f"exec={t_exec:6.3f}s  fetch={t_fetch:6.3f}s  "
              f"total={total:6.3f}s  {rate:8.0f} rows/s")

    avg = bench_small_queries(conn)
    print(f"small-query latency (execute+fetchone, pagesize=1): {avg*1000:.1f} ms avg")

    conn.close()


if __name__ == "__main__":
    main()
