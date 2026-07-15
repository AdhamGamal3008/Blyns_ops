"""Shared validation primitives."""

from __future__ import annotations

import re

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
