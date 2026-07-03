from __future__ import annotations

import csv
import shutil
import zipfile
from dataclasses import dataclass
from io import TextIOWrapper
from pathlib import Path
from typing import Iterable, Iterator

from .config import (
    CNAES_COLUMNS,
    EMPRESAS_COLUMNS,
    ESTABELECIMENTOS_COLUMNS,
    MOTIVOS_COLUMNS,
    MUNICIPIOS_COLUMNS,
    NATUREZAS_COLUMNS,
    RECEITA_DELIMITER,
    SIMPLES_COLUMNS,
)
from .utils import clean_cell


@dataclass(frozen=True)
class ReceitaSource:
    kind: str
    root_path: Path
    archive_members: tuple[str, ...] = ()
    processed: bool = True
    ignored_reason: str = ""

    @property
    def label(self) -> str:
        if self.archive_members:
            return f"{self.root_path.name}::{'::'.join(self.archive_members)}"
        return str(self.root_path)

    @property
    def size(self) -> int:
        if not self.archive_members:
            return self.root_path.stat().st_size
        with zipfile.ZipFile(self.root_path) as archive:
            return archive.getinfo(self.archive_members[0]).file_size


KIND_COLUMNS = {
    "empresas": EMPRESAS_COLUMNS,
    "estabelecimentos": ESTABELECIMENTOS_COLUMNS,
    "municipios": MUNICIPIOS_COLUMNS,
    "cnaes": CNAES_COLUMNS,
    "naturezas": NATUREZAS_COLUMNS,
    "motivos": MOTIVOS_COLUMNS,
    "simples": SIMPLES_COLUMNS,
}


def classify_receita_name(name: str) -> str | None:
    normalized = name.lower()
    if any(token in normalized for token in ("estabele", "estab", ".est")):
        return "estabelecimentos"
    if any(token in normalized for token in ("empresa", "empre", ".emp")):
        return "empresas"
    if "cnae" in normalized:
        return "cnaes"
    if any(token in normalized for token in ("munic", "municipio")):
        return "municipios"
    if any(token in normalized for token in ("natureza", "natju")):
        return "naturezas"
    if any(token in normalized for token in ("motivo", "moti")):
        return "motivos"
    if "simples" in normalized:
        return "simples"
    if any(token in normalized for token in ("pib", "populacao", "população", "ibge", "consolid")):
        return "consolidado"
    return None


def discover_receita_sources(raw_dirs: Iterable[Path]) -> tuple[list[ReceitaSource], list[ReceitaSource]]:
    processed: list[ReceitaSource] = []
    ignored: list[ReceitaSource] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add(source: ReceitaSource) -> None:
        key = (source.kind, str(source.root_path.resolve()), source.archive_members)
        if key in seen:
            return
        seen.add(key)
        if source.processed:
            processed.append(source)
        else:
            ignored.append(source)

    for raw_dir in raw_dirs:
        if raw_dir.is_file():
            candidates = [raw_dir]
        elif raw_dir.exists():
            candidates = [path for path in raw_dir.rglob("*") if path.is_file()]
        else:
            continue

        for path in candidates:
            kind = classify_receita_name(path.name)
            suffix = path.suffix.lower()
            if suffix == ".zip" or zipfile.is_zipfile(path):
                _discover_zip(path, add)
            elif kind in KIND_COLUMNS or kind == "consolidado":
                add(ReceitaSource(kind=kind, root_path=path))
            else:
                add(ReceitaSource(kind="desconhecido", root_path=path, processed=False, ignored_reason="nome nao classificado"))
    return processed, ignored


def _discover_zip(path: Path, add) -> None:
    outer_kind = classify_receita_name(path.name)
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos:
                add(ReceitaSource(kind=outer_kind or "desconhecido", root_path=path, processed=False, ignored_reason="zip vazio"))
                return
            for info in infos:
                member_kind = classify_receita_name(info.filename) or outer_kind
                if info.filename.lower().endswith(".zip"):
                    if member_kind in KIND_COLUMNS:
                        add(ReceitaSource(kind=member_kind, root_path=path, archive_members=(info.filename,)))
                    else:
                        add(
                            ReceitaSource(
                                kind="desconhecido",
                                root_path=path,
                                archive_members=(info.filename,),
                                processed=False,
                                ignored_reason="zip interno nao classificado",
                            )
                        )
                elif member_kind in KIND_COLUMNS:
                    add(ReceitaSource(kind=member_kind, root_path=path, archive_members=(info.filename,)))
                elif member_kind == "consolidado":
                    add(ReceitaSource(kind=member_kind, root_path=path, archive_members=(info.filename,)))
                else:
                    add(
                        ReceitaSource(
                            kind="desconhecido",
                            root_path=path,
                            archive_members=(info.filename,),
                            processed=False,
                            ignored_reason="membro nao classificado",
                        )
                    )
    except zipfile.BadZipFile:
        if outer_kind in KIND_COLUMNS:
            add(ReceitaSource(kind=outer_kind, root_path=path))
        else:
            add(ReceitaSource(kind="desconhecido", root_path=path, processed=False, ignored_reason="zip invalido"))


def iter_receita_rows(source: ReceitaSource, tmp_dir: Path) -> Iterator[dict[str, str]]:
    columns = KIND_COLUMNS[source.kind]
    for binary in _open_data_streams(source, tmp_dir):
        text = TextIOWrapper(binary, encoding="latin1", errors="replace", newline="")
        reader = csv.reader(text, delimiter=RECEITA_DELIMITER, quotechar='"')
        for row in reader:
            if not row:
                continue
            padded = row[: len(columns)] + [""] * max(0, len(columns) - len(row))
            yield {col: clean_cell(value) for col, value in zip(columns, padded)}


def _open_data_streams(source: ReceitaSource, tmp_dir: Path):
    if not source.archive_members:
        if source.root_path.suffix.lower() == ".zip":
            with zipfile.ZipFile(source.root_path) as archive:
                for info in archive.infolist():
                    if info.is_dir() or info.filename.lower().endswith(".zip"):
                        continue
                    with archive.open(info) as handle:
                        yield handle
        else:
            with source.root_path.open("rb") as handle:
                yield handle
        return

    tmp_dir.mkdir(parents=True, exist_ok=True)
    first_member = source.archive_members[0]
    with zipfile.ZipFile(source.root_path) as outer:
        if first_member.lower().endswith(".zip"):
            inner_path = _materialize_member_zip(source, tmp_dir, outer, first_member)
            with zipfile.ZipFile(inner_path) as inner:
                for info in inner.infolist():
                    if info.is_dir():
                        continue
                    if info.filename.lower().endswith(".zip"):
                        nested_path = tmp_dir / _safe_name(f"{inner_path.stem}_{Path(info.filename).name}")
                        if not nested_path.exists() or nested_path.stat().st_size != info.file_size:
                            with inner.open(info) as src, nested_path.open("wb") as dst:
                                shutil.copyfileobj(src, dst, length=1024 * 1024)
                        with zipfile.ZipFile(nested_path) as nested:
                            for nested_info in nested.infolist():
                                if not nested_info.is_dir():
                                    with nested.open(nested_info) as handle:
                                        yield handle
                    else:
                        with inner.open(info) as handle:
                            yield handle
        else:
            with outer.open(first_member) as handle:
                yield handle


def _materialize_member_zip(source: ReceitaSource, tmp_dir: Path, outer: zipfile.ZipFile, member: str) -> Path:
    info = outer.getinfo(member)
    target = tmp_dir / _safe_name(f"{source.root_path.stem}_{Path(member).name}")
    if target.exists() and target.stat().st_size == info.file_size:
        return target
    with outer.open(member) as src, target.open("wb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
    return target


def _safe_name(name: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
