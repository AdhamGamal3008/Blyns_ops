"""Generic CSV import/export primitives. No module knowledge lives here.

A single `CsvField` list per entity is the source of truth for three things —
the downloadable template's headers, the export column list, and the import
parser — so those three can never drift apart. A module supplies the field
specs (see `modules/crm/csv_schema.py`); everything in this file is
domain-agnostic and reusable by any other module that wants the same surface.

Two deliberate choices:

* **Excel compatibility.** Exports lead with a UTF-8 BOM (Excel mis-decodes
  UTF-8 without one) and use CRLF per RFC 4180; imports strip the BOM and fall
  back to cp1252 for files Excel saved as "CSV (Comma delimited)" on Windows.
* **ISO-8601 dates only.** `03/04/2026` means two different days either side of
  the Atlantic, so a locale-ambiguous date is rejected with a message naming the
  expected format rather than silently misread as a delivery or close date.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from typing import Any, Literal

from app.shared.validation import EMAIL_PATTERN

BOM = "﻿"
LINE_TERMINATOR = "\r\n"

CsvKind = Literal[
    "str", "email", "enum", "int", "float", "bool", "date", "datetime", "list",
]


@dataclass(frozen=True)
class CsvField:
    """One CSV column, and everything both directions need to know about it."""

    key: str
    """Logical name. The import maps a parsed cell onto this; the export reads it."""

    header: str
    """The column heading a user sees in the template and the export."""

    kind: CsvKind = "str"
    required: bool = False

    choices: tuple[str, ...] = ()
    """Accepted values for `enum`, as shown to the user."""

    import_choices: tuple[str, ...] | None = None
    """Narrower accepted set on import — e.g. a lead's `converted` status is a
    workflow outcome that can be exported but never typed into a spreadsheet."""

    importable: bool = True
    exportable: bool = True

    example: str = ""
    """Sample value for the annotated template."""

    hint: str = ""
    """One line of guidance surfaced in the import dialog."""

    @property
    def accepted(self) -> tuple[str, ...]:
        return self.import_choices if self.import_choices is not None else self.choices


class CellError(ValueError):
    """One cell could not be read as its field's kind. Becomes a `RowIssue`."""


class CsvFormatError(ValueError):
    """The file as a whole is unusable (undecodable, headerless, missing a
    required column). Callers surface this as a 422 — nothing is imported."""


@dataclass
class RowIssue:
    row: int
    """1-based line number as the user sees it in their spreadsheet — the header
    is line 1, so the first data row is line 2."""

    column: str | None
    value: str
    message: str


@dataclass
class ParsedRow:
    row: int
    values: dict[str, Any]
    """Coerced values keyed by `CsvField.key`. Only columns actually present in
    the uploaded file appear — an absent column must not overwrite stored data."""


@dataclass
class ParseResult:
    rows: list[ParsedRow] = dataclass_field(default_factory=list)
    """Rows that read cleanly. A row with even one bad cell is held back in
    `issues` instead — a half-read row must never reach the database."""

    issues: list[RowIssue] = dataclass_field(default_factory=list)
    seen_rows: int = 0
    """Every non-blank data row, sound or not — the denominator in the report."""

    present: list[str] = dataclass_field(default_factory=list)
    """Field keys whose header was found in the file."""

    unknown_headers: list[str] = dataclass_field(default_factory=list)
    """Columns we ignored, echoed back so a typo'd heading is visible."""


# --- writing -----------------------------------------------------------------

_TRUE = frozenset({"true", "yes", "y", "1"})
_FALSE = frozenset({"false", "no", "n", "0"})
_NUMBER_NOISE = re.compile(r"[,\s $€£%]")


def line(values: Iterable[Any]) -> str:
    """One RFC 4180 record, quoted as needed."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator=LINE_TERMINATOR).writerow(list(values))
    return buf.getvalue()


def format_cell(f: CsvField, value: Any) -> str:
    """Render a stored value so that re-importing it yields the same value."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=UTC)
        if f.kind == "date":
            return moment.astimezone(UTC).date().isoformat()
        return moment.astimezone(UTC).isoformat()
    if isinstance(value, list | tuple):
        return "; ".join(str(v) for v in value)
    if isinstance(value, float):
        # 25000.0 → "25000", so a whole amount doesn't grow a decimal tail on
        # every export/import round trip.
        return str(int(value)) if value == int(value) else str(value)
    return str(value)


def header_line(fields: Iterable[CsvField]) -> str:
    return BOM + line(f.header for f in fields)


def data_line(fields: Iterable[CsvField], row: dict[str, Any]) -> str:
    fields = list(fields)
    return line(format_cell(f, row.get(f.key)) for f in fields)


def template_text(fields: Iterable[CsvField], *, sample: bool = False) -> str:
    """Header row for the import template, optionally over one example row."""
    fields = [f for f in fields if f.importable]
    out = header_line(fields)
    if sample:
        out += line(f.example for f in fields)
    return out


def export_text(fields: Iterable[CsvField], rows: Iterable[dict[str, Any]]) -> str:
    """Whole-file export. Streaming callers use `header_line`/`data_line`."""
    fields = list(fields)
    return header_line(fields) + "".join(data_line(fields, row) for row in rows)


# --- reading -----------------------------------------------------------------

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S")


def normalize_header(raw: str) -> str:
    """`"Account Name"`, `"account_name"` and `"ACCOUNT-NAME"` are one column."""
    return re.sub(r"[^a-z0-9]+", "_", raw.strip().lower()).strip("_")


def _to_datetime(text: str) -> datetime:
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        for fmt in _DATE_FORMATS:
            try:
                moment = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            raise CellError(
                f"“{text}” is not a date we can read — use YYYY-MM-DD "
                "(a slashed date like 03/04/2026 is ambiguous)"
            ) from None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def coerce(f: CsvField, raw: str) -> Any:
    """Read one cell, or raise `CellError` naming what is wrong with it."""
    text = (raw or "").strip()
    if text == "":
        if f.required:
            raise CellError("required — this column cannot be left blank")
        return None

    if f.kind == "str":
        return text
    if f.kind == "email":
        value = text.lower()
        if not EMAIL_PATTERN.match(value):
            raise CellError(f"“{text}” is not a valid email address")
        return value
    if f.kind == "enum":
        value = text.lower()
        if value not in f.accepted:
            raise CellError(f"“{text}” is not one of: {', '.join(f.accepted)}")
        return value
    if f.kind == "bool":
        value = text.lower()
        if value in _TRUE:
            return True
        if value in _FALSE:
            return False
        raise CellError(f"“{text}” is not a yes/no value")
    if f.kind in ("int", "float"):
        cleaned = _NUMBER_NOISE.sub("", text)
        try:
            return int(cleaned) if f.kind == "int" else float(cleaned)
        except ValueError:
            raise CellError(f"“{text}” is not a number") from None
    if f.kind in ("date", "datetime"):
        return _to_datetime(text)
    if f.kind == "list":
        # Semicolons are the documented separator; a comma only survives here
        # inside an already-quoted cell, so splitting on both is safe.
        return [part.strip() for part in re.split(r"[;,]", text) if part.strip()]
    return text


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CsvFormatError(
        "This file is not readable text. Export it again as CSV (UTF-8)."
    )


_DELIMITERS = (",", ";", "\t", "|")


def _pick_delimiter(header_line: str, known: dict[str, CsvField]) -> str:
    """Excel writes `;` in several locales, and `csv.Sniffer` gives up whenever
    a row's field count wobbles — which is exactly what an unquoted list cell
    does. Scoring each candidate by how many headings it actually resolves uses
    the signal we already hold, and ties break toward the comma.
    """
    best, best_score = ",", -1
    for delimiter in _DELIMITERS:
        try:
            cells = next(csv.reader([header_line], delimiter=delimiter))
        except csv.Error:
            continue
        score = sum(1 for cell in cells if normalize_header(cell) in known)
        if score > best_score:
            best, best_score = delimiter, score
    return best


def parse(
    data: bytes, fields: Iterable[CsvField], *, max_rows: int
) -> ParseResult:
    """Read an uploaded file against a field spec.

    Cell-level problems become `RowIssue`s so the good rows can still be
    imported; anything that makes the whole file unusable raises
    `CsvFormatError`.
    """
    importable = [f for f in fields if f.importable]
    by_header = {normalize_header(f.header): f for f in importable}

    text = _decode(data)
    if not text.strip():
        raise CsvFormatError("The file is empty.")

    first_line = next((ln for ln in text.splitlines() if ln.strip()), "")
    reader = csv.reader(
        io.StringIO(text, newline=""), delimiter=_pick_delimiter(first_line, by_header)
    )
    try:
        header = next(reader)
    except StopIteration:
        raise CsvFormatError("The file has no header row.") from None

    columns: list[CsvField | None] = []
    result = ParseResult()
    seen: set[str] = set()
    for raw in header:
        name = normalize_header(raw)
        f = by_header.get(name)
        if f is None:
            columns.append(None)
            if raw.strip():
                result.unknown_headers.append(raw.strip())
            continue
        if f.key in seen:
            raise CsvFormatError(f"The column “{f.header}” appears more than once.")
        seen.add(f.key)
        columns.append(f)
        result.present.append(f.key)

    missing = [f.header for f in importable if f.required and f.key not in seen]
    if missing:
        raise CsvFormatError(
            "The file is missing required column(s): " + ", ".join(missing)
            + ". Download the template and paste your data under its headings."
        )
    if not result.present:
        raise CsvFormatError(
            "No recognisable columns. Download the template and use its headings."
        )

    for offset, raw_row in enumerate(reader):
        row_no = offset + 2  # header is line 1
        if not any((cell or "").strip() for cell in raw_row):
            continue  # blank spacer row
        result.seen_rows += 1
        if result.seen_rows > max_rows:
            raise CsvFormatError(
                f"This file has more than {max_rows} rows. "
                "Split it and import the parts separately."
            )

        values: dict[str, Any] = {}
        sound = True
        for index, f in enumerate(columns):
            if f is None:
                continue
            cell = raw_row[index] if index < len(raw_row) else ""
            try:
                values[f.key] = coerce(f, cell)
            except CellError as exc:
                sound = False
                result.issues.append(
                    RowIssue(row_no, f.header, (cell or "").strip(), str(exc))
                )
        if sound:
            result.rows.append(ParsedRow(row_no, values))

    return result


def issue_rows(issues: Iterable[RowIssue]) -> Iterator[list[str]]:
    """Flatten issues for a "rows that failed" report."""
    for issue in issues:
        yield [str(issue.row), issue.column or "", issue.value, issue.message]
