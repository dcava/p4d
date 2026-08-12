from setuptools import setup, find_packages

setup(
    zip_safe=False,
    name="p4d",
    version="2.2.1",
    install_requires=["cffi", "python-dateutil"],
    setup_requires=["cffi", "python-dateutil"],
    cffi_modules=["p4d/_build_ffi.py:ffi"],
    packages=find_packages(),
    package_data={"p4d": ["py_fourd.h"]},
    author="David Cavallucci",
    author_email="david.cavallucci@gmail.com",
    url="https://github.com/dcava/p4d",
    description="Python DB API 2.0 driver for the 4D database server",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    license="MIT",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Developers",
        "Topic :: Database",
        "Programming Language :: Python :: 3",
    ],
    keywords="database drivers DBI 4d",
    python_requires=">=3.8",
)
