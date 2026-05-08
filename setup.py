from setuptools import setup, find_packages

setup(
    zip_safe=False,
    name="p4d",
    version="1.9",
    install_requires=["cffi", "python-dateutil"],
    setup_requires=["cffi", "python-dateutil"],
    cffi_modules=["p4d/_build_ffi.py:ffi"],
    packages=find_packages(),
    package_data={'p4d': ['py_fourd.h']},
    author="Israel Brewster",
    author_email="israel@brewstersoft.com",
    url="https://github.com/ibrewster/p4d",
    description="Python DBI module for the 4D database",
    long_description=(
        "This module provides a Python Database API v2.0 compliant driver for the 4D "
        "(4th Dimension, http://www.4d.com) database. Based off of C library code provided "
        "by 4th Dimension and implemented using CFFI."
    ),
    license='BSD',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: BSD License',
        'Intended Audience :: Developers',
        'Topic :: Database',
        'Programming Language :: Python :: 3',
    ],
    keywords='database drivers DBI 4d',
)
