#!/usr/bin/env python3
"""
Setup script for SMPTE Timecode Server
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="smpte-timecode-server",
    version="1.0.0",
    author="Claude",
    author_email="claude@anthropic.com",
    description="SMPTE Timecode Server with multi-session support and various framerates",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/smpte-timecode-server",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Multimedia :: Video",
        "Topic :: System :: Networking",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "aioconsole>=0.6.2",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21.0",
            "black>=22.0",
            "flake8>=4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "smpte-server=smpte_server_python:main",
            "smpte-client=smpte_client_python:main",
        ],
    },
    keywords="smpte timecode broadcast video synchronization tcp server",
    project_urls={
        "Bug Reports": "https://github.com/example/smpte-timecode-server/issues",
        "Source": "https://github.com/example/smpte-timecode-server",
    },
)
