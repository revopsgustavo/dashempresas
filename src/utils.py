import csv
import re
import unicodedata
from pathlib import Path

from .config import ENCODINGS


def ensure_dirs(*paths: Path) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip().upper()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"\s+", " ", text)
    return text


def only_digits(value: object) -> str:
    return re.sub(r"\D+", "", "" if value is None else str(value))


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).replace("\ufeff", "").strip()


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()[:4096]
    for encoding in ENCODINGS:
        try:
            raw.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return "latin1"


def read_header(path: Path) -> tuple[str, list[str]]:
    encoding = detect_encoding(path)
    with path.open("r", encoding=encoding, newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"
        reader = csv.reader(handle, dialect)
        header = next(reader, [])
    return encoding, [clean_cell(col) for col in header]


def write_csv(path: Path, columns: list[str], rows) -> int:
    count = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=",")
        writer.writerow(columns)
        for row in rows:
            writer.writerow([clean_cell(row.get(col, "")) for col in columns])
            count += 1
    return count
