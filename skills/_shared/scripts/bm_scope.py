#!/usr/bin/env python3
"""Validação e selo determinístico do intake de escopo em PDF."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bm_project_model import read_frontmatter
from bm_workspace import MethodWorkspace


MAX_PDF_BYTES = 128 * 1024 * 1024
MAX_SCOPE_BYTES = 512 * 1024
EXTRACTION_MODES = frozenset({"native", "ocr", "mixed"})
REQUIRED_SECTIONS = (
    "Objetivo",
    "Resultados esperados",
    "Atores e perfis",
    "Fluxos",
    "Requisitos funcionais",
    "Requisitos não funcionais",
    "Regras de negócio",
    "Dados e estados",
    "Integrações e efeitos externos",
    "Critérios gerais de aceite",
    "Comportamentos de erro",
    "Riscos e casos para o planejamento",
    "Dentro do escopo",
    "Fora do escopo",
    "Decisões consolidadas",
    "Questões abertas",
    "Decisões bloqueantes",
    "Contradições",
    "Proveniência e cobertura",
)
CLOSED_SECTIONS = (
    "Questões abertas",
    "Decisões bloqueantes",
    "Contradições",
)
STRUCTURED_SECTIONS = {
    "Atores e perfis": "ACT",
    "Fluxos": "FLW",
    "Requisitos funcionais": "REQ",
    "Requisitos não funcionais": "NFR",
    "Regras de negócio": "BR",
    "Dados e estados": "DAT",
    "Integrações e efeitos externos": "INT",
    "Comportamentos de erro": "ERR",
    "Riscos e casos para o planejamento": "RSK",
    "Decisões consolidadas": "DEC",
}
ITEM_PATTERN = re.compile(
    r"(?m)^### ((?:ACT|FLW|REQ|NFR|BR|DAT|INT|ERR|RSK|DEC)-[0-9]{3})\b[^\n]*$"
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\?\?+"),
    re.compile(r"\ba definir\b", re.IGNORECASE),
    re.compile(r"\bquando necessári[oa]s?\b", re.IGNORECASE),
    re.compile(r"\bconforme necessári[oa]s?\b", re.IGNORECASE),
    re.compile(r"\be similares\b", re.IGNORECASE),
    re.compile(r"\betc\.?\b", re.IGNORECASE),
    re.compile(r"\bdeve funcionar\b", re.IGNORECASE),
    re.compile(r"\btratar erros\b", re.IGNORECASE),
)


class ScopeError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pdf_metadata(source: Path) -> dict[str, str]:
    if source.is_symlink() or not source.is_file():
        raise ScopeError("SCOPE_SOURCE_INVALID", "fonte PDF ausente ou symlink")
    if source.suffix.lower() != ".pdf":
        raise ScopeError("SCOPE_SOURCE_INVALID", "fonte deve possuir extensão .pdf")
    size = source.stat().st_size
    if size <= 8 or size > MAX_PDF_BYTES:
        raise ScopeError("SCOPE_SOURCE_INVALID", "fonte PDF vazia ou acima de 128 MiB")
    with source.open("rb") as stream:
        if not stream.read(5).startswith(b"%PDF-"):
            raise ScopeError("SCOPE_SOURCE_INVALID", "assinatura PDF inválida")
    if re.fullmatch(r"[^/\\\x00-\x1f]+\.pdf", source.name, re.IGNORECASE) is None:
        raise ScopeError("SCOPE_SOURCE_INVALID", "nome do PDF é inválido")
    return {"name": source.name, "sha256": _sha256(source)}


def _scope_directory(workspace: MethodWorkspace, change: str) -> Path:
    if not re.fullmatch(r"C[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*", change):
        raise ScopeError("SCOPE_CHANGE_INVALID", f"mudança inválida: {change}")
    directory = workspace.resolve(f"changes/{change}")
    if directory.is_symlink() or not directory.is_dir():
        raise ScopeError("SCOPE_CHANGE_INVALID", f"mudança não encontrada: {change}")
    return directory


def _sections(body: str) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    title = re.match(r"\A# Escopo(?:\s+[-—:].+)?\s*\n", body)
    if title is None:
        raise ScopeError("SCOPE_FORMAT_INVALID", "documento deve iniciar com # Escopo")
    matches = list(re.finditer(r"(?m)^## ([^\n]+?)\s*$", body))
    names = [match.group(1).strip() for match in matches]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ScopeError(
            "SCOPE_FORMAT_INVALID", f"seção duplicada: {duplicates[0]}"
        )
    unknown = [name for name in names if name not in REQUIRED_SECTIONS]
    if unknown:
        raise ScopeError("SCOPE_FORMAT_INVALID", f"seção desconhecida: {unknown[0]}")
    missing = [name for name in REQUIRED_SECTIONS if name not in names]
    if missing:
        raise ScopeError("SCOPE_FORMAT_INVALID", f"seção obrigatória ausente: {missing[0]}")
    if tuple(names) != REQUIRED_SECTIONS:
        raise ScopeError("SCOPE_FORMAT_INVALID", "seções fora da ordem canônica")
    values: dict[str, str] = {}
    positions: dict[str, tuple[int, int]] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        name = match.group(1).strip()
        values[name] = body[start:end].strip()
        positions[name] = (start, end)
    for name, value in values.items():
        if not value:
            raise ScopeError("SCOPE_FORMAT_INVALID", f"seção vazia: {name}")
    return values, positions


def _page_references(value: str, pages: int) -> list[int]:
    referenced: list[int] = []
    pattern = re.compile(r"PDF p(?:\.|p\.)\s*([0-9]+)(?:\s*[-–]\s*([0-9]+))?")
    for match in pattern.finditer(value):
        first = int(match.group(1))
        last = int(match.group(2) or first)
        if first < 1 or last < first:
            raise ScopeError("SCOPE_SOURCE_INVALID", "intervalo de páginas inválido")
        for page in range(first, last + 1):
            if page > pages:
                raise ScopeError(
                    "SCOPE_SOURCE_INVALID", f"página {page} fora do PDF de {pages} páginas"
                )
            referenced.append(page)
    return referenced


def _source_pages(value: str, pages: int) -> list[int]:
    if value.lower() == "decisão do usuário":
        return []
    if re.fullmatch(r"PDF p\. [0-9]+", value):
        return _page_references(value, pages)
    if re.fullmatch(r"PDF pp\. [0-9]+\s*[-–]\s*[0-9]+", value):
        return _page_references(value, pages)
    raise ScopeError(
        "SCOPE_SOURCE_INVALID",
        "fonte deve ser PDF p. N, PDF pp. N-M ou decisão do usuário",
    )


def _item_blocks(body: str) -> list[tuple[str, str]]:
    matches = list(ITEM_PATTERN.finditer(body))
    identifiers = [match.group(1) for match in matches]
    duplicates = sorted({value for value in identifiers if identifiers.count(value) > 1})
    if duplicates:
        raise ScopeError("SCOPE_FORMAT_INVALID", f"ID duplicado: {duplicates[0]}")
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        next_item = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        next_section = body.find("\n## ", match.end())
        end = min(next_item, next_section) if next_section >= 0 else next_item
        blocks.append((match.group(1), body[match.start() : end].strip()))
    return blocks


def _replace_provenance(body: str, value: str) -> str:
    _sections(body)
    marker = "## Proveniência e cobertura"
    start = body.index(marker)
    return body[:start].rstrip() + "\n\n" + marker + "\n\n" + value.strip() + "\n"


def _validate_body(body: str, pages: int) -> tuple[str, dict[str, int]]:
    if body.startswith("---"):
        raise ScopeError(
            "SCOPE_FORMAT_INVALID", "draft não pode fornecer frontmatter; o CLI gera o selo"
        )
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_SCOPE_BYTES:
        raise ScopeError("SCOPE_FORMAT_INVALID", "SCOPE.md excede 512 KiB")
    normalized = body.replace("\r\n", "\n").strip() + "\n"
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(normalized):
            raise ScopeError(
                "SCOPE_AMBIGUOUS", f"placeholder ou linguagem vaga encontrada: {pattern.pattern}"
            )
    sections, _ = _sections(normalized)
    for name in ("Objetivo", "Resultados esperados", "Dentro do escopo", "Fora do escopo"):
        if len(sections[name]) < 20:
            raise ScopeError("SCOPE_FORMAT_INVALID", f"seção insuficiente: {name}")
    for name in CLOSED_SECTIONS:
        if sections[name] != "Nenhuma.":
            label = {
                "Questões abertas": "questão aberta",
                "Decisões bloqueantes": "decisão bloqueante",
                "Contradições": "contradição aberta",
            }[name]
            raise ScopeError("SCOPE_AMBIGUOUS", f"{label} impede o selo")

    for section_name, prefix in STRUCTURED_SECTIONS.items():
        section = sections[section_name]
        identifiers = ITEM_PATTERN.findall(section)
        if identifiers:
            wrong = next(
                (identifier for identifier in identifiers if not identifier.startswith(f"{prefix}-")),
                None,
            )
            if wrong:
                raise ScopeError(
                    "SCOPE_FORMAT_INVALID",
                    f"{wrong} está na seção incorreta: {section_name}",
                )
            continue
        allowed_absence = (
            section == "Nenhuma."
            or section == "Não especificado no PDF."
            or re.fullmatch(r"Não aplicável:\s*\S.*", section, re.DOTALL) is not None
        )
        if not allowed_absence:
            raise ScopeError(
                "SCOPE_FORMAT_INVALID",
                f"{section_name} exige item {prefix} ou ausência explícita",
            )

    blocks = _item_blocks(normalized)
    if not any(identifier.startswith("REQ-") for identifier, _ in blocks):
        raise ScopeError("SCOPE_FORMAT_INVALID", "ao menos um REQ é obrigatório")
    unsourced: list[str] = []
    referenced_pages: list[int] = []
    for identifier, block in blocks:
        source_match = re.search(r"(?m)^- Fonte:\s*(.+?)\s*$", block)
        if source_match is None:
            unsourced.append(identifier)
            continue
        source_value = source_match.group(1)
        item_pages = _source_pages(source_value, pages)
        referenced_pages.extend(item_pages)
        if identifier.startswith(("REQ-", "NFR-")):
            if not re.search(r"(?m)^- Aceite:\s*$", block):
                raise ScopeError(
                    "SCOPE_FORMAT_INVALID", f"{identifier} exige bloco de aceite"
                )
            if not all(token in block for token in ("GIVEN", "WHEN", "THEN")):
                raise ScopeError(
                    "SCOPE_AMBIGUOUS", f"{identifier} exige aceite GIVEN/WHEN/THEN"
                )
        if identifier.startswith("FLW-"):
            for field in (
                "Ator",
                "Gatilho",
                "Pré-condições",
                "Caminho principal",
                "Resultado",
                "Falhas",
            ):
                if not re.search(rf"(?m)^- {re.escape(field)}:\s*\S", block):
                    raise ScopeError(
                        "SCOPE_FORMAT_INVALID", f"{identifier} exige campo {field}"
                    )
    if unsourced:
        raise ScopeError("SCOPE_SOURCE_INVALID", f"item sem fonte: {unsourced[0]}")
    if not referenced_pages:
        raise ScopeError("SCOPE_SOURCE_INVALID", "nenhuma página do PDF foi referenciada")

    coverage = {
        "identified_items": len(blocks),
        "sourced_items": len(blocks),
        "unsourced_items": 0,
        "open_questions": 0,
        "blocking_decisions": 0,
        "open_contradictions": 0,
    }
    provenance = (
        f"- Páginas processadas: 1-{pages} de {pages}.\n"
        f"- Itens estruturados: {coverage['identified_items']}\n"
        "- Itens sem fonte: 0\n"
        "- Questões abertas: 0\n"
        "- Decisões bloqueantes: 0\n"
        "- Contradições abertas: 0"
    )
    return _replace_provenance(normalized, provenance), coverage


def _digest(metadata: dict[str, Any], body: str) -> str:
    encoded = json.dumps(
        metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded + b"\n" + body.encode("utf-8")).hexdigest()


def _document(metadata: dict[str, Any], body: str) -> str:
    frontmatter = json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2)
    return f"---\n{frontmatter}\n---\n\n{body.rstrip()}\n"


def seal_scope(
    repo: Path,
    change: str,
    source: Path,
    draft: Path,
    pages: int,
    extraction: str,
) -> dict[str, Any]:
    if pages < 1 or pages > 10000:
        raise ScopeError("SCOPE_SOURCE_INVALID", "quantidade de páginas inválida")
    if extraction not in EXTRACTION_MODES:
        raise ScopeError("SCOPE_SOURCE_INVALID", "modo de extração inválido")
    if draft.is_symlink() or not draft.is_file():
        raise ScopeError("SCOPE_FORMAT_INVALID", "draft ausente ou symlink")
    source_metadata = _pdf_metadata(source)
    body, coverage = _validate_body(draft.read_text(encoding="utf-8"), pages)

    workspace = MethodWorkspace(repo)
    state = workspace.read_state()
    active = state.get("active_work")
    if not isinstance(active, dict) or active.get("kind") != "change":
        raise ScopeError("SCOPE_CHANGE_INVALID", "não existe mudança ativa")
    if active.get("id") != change:
        raise ScopeError("SCOPE_CHANGE_INVALID", "mudança informada não é a ativa")
    if (
        state.get("status") not in {"planning", "scope_ready"}
        or active.get("status") not in {"planning", "scope_ready"}
    ):
        raise ScopeError("SCOPE_CHANGE_INVALID", "mudança já avançou além do intake")
    directory = _scope_directory(workspace, change)
    scope_path = directory / "SCOPE.md"
    metadata: dict[str, Any] = {
        "schema_version": 1,
        "document": "bianchini-scope",
        "status": "ready_for_sdd",
        "change": change,
        "source": {
            "kind": "pdf",
            **source_metadata,
            "pages": pages,
            "extraction": extraction,
        },
        "coverage": coverage,
        "sealed_at": _now(),
    }
    metadata["scope_digest"] = _digest(metadata, body)
    previous = scope_path.read_bytes() if scope_path.exists() else None
    workspace.atomic_write(scope_path, _document(metadata, body))
    try:
        active["status"] = "scope_ready"
        state.update(
            {
                "active_work": active,
                "current_unit": "scope",
                "status": "scope_ready",
                "blockers": [],
                "next_action": f"Executar /sdd-planning para {change}.",
                "digest": metadata["scope_digest"],
                "updated_at": _now(),
            }
        )
        state.setdefault("pointers", {})["scope"] = (
            f".bianchini/changes/{change}/SCOPE.md"
        )
        workspace.write_state(state)
    except Exception:
        if previous is None:
            scope_path.unlink(missing_ok=True)
        else:
            workspace.atomic_write(scope_path, previous)
        raise
    return {
        "change": change,
        "status": "ready_for_sdd",
        "scope": str(scope_path),
        "scope_digest": metadata["scope_digest"],
        "source_sha256": source_metadata["sha256"],
        "coverage": coverage,
        "next_action": "/sdd-planning",
    }


def verify_scope(repo: Path, change: str, source: Path | None = None) -> dict[str, Any]:
    workspace = MethodWorkspace(repo)
    state = workspace.read_state()
    directory = _scope_directory(workspace, change)
    scope_path = directory / "SCOPE.md"
    try:
        metadata = read_frontmatter(scope_path)
    except ValueError as error:
        raise ScopeError("SCOPE_FORMAT_INVALID", str(error)) from error
    expected_keys = {
        "schema_version",
        "document",
        "status",
        "change",
        "source",
        "coverage",
        "sealed_at",
        "scope_digest",
    }
    if set(metadata) != expected_keys:
        raise ScopeError("SCOPE_FORMAT_INVALID", "frontmatter do SCOPE.md é inválido")
    if (
        metadata.get("schema_version") != 1
        or metadata.get("document") != "bianchini-scope"
        or metadata.get("status") != "ready_for_sdd"
        or metadata.get("change") != change
    ):
        raise ScopeError("SCOPE_FORMAT_INVALID", "identidade do SCOPE.md é inválida")
    source_info = metadata.get("source")
    if not isinstance(source_info, dict) or set(source_info) != {
        "kind",
        "name",
        "sha256",
        "pages",
        "extraction",
    }:
        raise ScopeError("SCOPE_FORMAT_INVALID", "metadados da fonte são inválidos")
    if (
        source_info.get("kind") != "pdf"
        or isinstance(source_info.get("pages"), bool)
        or not isinstance(source_info.get("pages"), int)
        or not 1 <= source_info["pages"] <= 10000
        or source_info.get("extraction") not in EXTRACTION_MODES
        or not isinstance(source_info.get("name"), str)
        or not source_info["name"].lower().endswith(".pdf")
        or Path(source_info["name"]).name != source_info["name"]
        or not re.fullmatch(r"[0-9a-f]{64}", str(source_info.get("sha256", "")))
    ):
        raise ScopeError("SCOPE_FORMAT_INVALID", "fonte selada é inválida")
    text = scope_path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n.*?\r?\n---\r?\n\r?\n(.*)\Z", text, re.DOTALL)
    if match is None:
        raise ScopeError("SCOPE_FORMAT_INVALID", "corpo do SCOPE.md ausente")
    body, coverage = _validate_body(match.group(1), int(source_info["pages"]))
    if body != match.group(1).replace("\r\n", "\n"):
        raise ScopeError("SCOPE_FORMAT_INVALID", "corpo do SCOPE.md não está normalizado")
    if metadata.get("coverage") != coverage:
        raise ScopeError("SCOPE_FORMAT_INVALID", "cobertura selada diverge do documento")
    digest = metadata.get("scope_digest")
    unsigned = {key: value for key, value in metadata.items() if key != "scope_digest"}
    expected_digest = _digest(unsigned, body)
    if digest != expected_digest:
        raise ScopeError("SCOPE_STALE", "digest do SCOPE.md diverge do conteúdo")
    if source is not None:
        current = _pdf_metadata(source)
        if current["sha256"] != source_info["sha256"]:
            raise ScopeError("SCOPE_STALE", "fonte PDF diverge do selo")
    active = state.get("active_work")
    if isinstance(active, dict) and active.get("id") == change and (
        state.get("status") == "scope_ready" or active.get("status") == "scope_ready"
    ):
        expected_pointer = f".bianchini/changes/{change}/SCOPE.md"
        if (
            state.get("status") != "scope_ready"
            or active.get("status") != "scope_ready"
            or state.get("digest") != digest
            or state.get("pointers", {}).get("scope") != expected_pointer
        ):
            raise ScopeError("SCOPE_STALE", "STATE.md diverge do escopo selado")
    return {
        "change": change,
        "status": "ready_for_sdd",
        "scope": str(scope_path),
        "scope_digest": digest,
        "source_sha256": source_info["sha256"],
        "coverage": coverage,
        "verified": True,
    }


__all__ = ["ScopeError", "seal_scope", "verify_scope"]
