from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .config import RAW_DIR


@dataclass(frozen=True)
class DataSource:
    kind: str
    path: Path
    members: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        if self.members:
            return f"{self.path.name}::{'::'.join(self.members)}"
        return self.path.name


def classify_name(name: str) -> str | None:
    normalized = name.lower()
    if any(token in normalized for token in ("estabele", ".estab", "estab")):
        return "estabelecimentos"
    if any(token in normalized for token in ("empresa", ".empre", "empre")):
        return "empresas"
    if "cnae" in normalized:
        return "cnaes"
    if "munic" in normalized:
        return "municipios"
    if any(token in normalized for token in ("natureza", "natju", "nat_jurid")):
        return "naturezas"
    if "simples" in normalized:
        return "simples"
    if any(token in normalized for token in ("pib", "populacao", "população", "ibge", "consolid")):
        return "consolidado"
    return None


def discover_sources(raw_dir: Path = RAW_DIR) -> list[DataSource]:
    sources: list[DataSource] = []
    if not raw_dir.exists():
        return sources

    for path in raw_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() == ".zip":
            sources.extend(_discover_zip(path))
            continue
        kind = classify_name(str(path.relative_to(raw_dir)))
        if kind:
            sources.append(DataSource(kind=kind, path=path))
    return sources


def _discover_zip(path: Path, parents: tuple[str, ...] = ()) -> list[DataSource]:
    found: list[DataSource] = []
    context = parents or (path.name,)
    with zipfile.ZipFile(path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            actual_chain = parents + (info.filename,)
            classify_chain = context + (info.filename,)
            kind = classify_name("/".join(classify_chain))
            if info.filename.lower().endswith(".zip"):
                data = archive.read(info)
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    for nested_info in nested.infolist():
                        if nested_info.is_dir():
                            continue
                        nested_actual_chain = actual_chain + (nested_info.filename,)
                        nested_classify_chain = classify_chain + (nested_info.filename,)
                        nested_kind = classify_name("/".join(nested_classify_chain))
                        if nested_kind:
                            found.append(DataSource(kind=nested_kind, path=path, members=nested_actual_chain))
            elif kind:
                found.append(DataSource(kind=kind, path=path, members=actual_chain))
    return found


def open_binary(source: DataSource):
    if not source.members:
        return source.path.open("rb")

    data: bytes | None = None
    current_archive = zipfile.ZipFile(source.path)
    try:
        for index, member in enumerate(source.members):
            data = current_archive.read(member)
            current_archive.close()
            if index == len(source.members) - 1:
                return io.BytesIO(data)
            current_archive = zipfile.ZipFile(io.BytesIO(data))
    except Exception:
        current_archive.close()
        raise
    raise FileNotFoundError(source.label)


def sources_by_kind(sources: list[DataSource], kind: str) -> Iterator[DataSource]:
    yield from (source for source in sources if source.kind == kind)
