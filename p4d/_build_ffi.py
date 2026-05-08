"""
Build script for the out-of-line CFFI extension.

During installation this is invoked automatically via the cffi_modules
entry in setup.py.

For development builds run from the repo root:
    python p4d/_build_ffi.py
"""

import os
import glob
from cffi import FFI

ffi = FFI()

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

with open(os.path.join(_HERE, 'py_fourd.h')) as f:
    ffi.cdef(f.read())

ffi.set_source(
    "p4d._p4d_cffi",
    '#include "fourd.h"',
    sources=sorted(glob.glob(os.path.join(_ROOT, 'lib4d_sql', '*.c'))),
    include_dirs=[os.path.join(_ROOT, 'lib4d_sql')],
)

if __name__ == '__main__':
    ffi.compile(verbose=True)
