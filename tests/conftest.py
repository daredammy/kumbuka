"""Pytest configuration for kumbuka tests."""

import os

# Prevent tests from loading the user's actual env file
os.environ.setdefault("KUMBUKA_OUTPUT_DIR", "/tmp/kumbuka-test")
