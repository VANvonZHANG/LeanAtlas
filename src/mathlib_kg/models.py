"""Data structures for structure.jsonl and extract.jsonl records."""
from datetime import date
from typing import Optional

import msgspec


class Import(msgspec.Struct):
    name: str
    isPublic: bool = False
    isDeprecated: bool = False


class Declaration(msgspec.Struct):
    # 必填字段在前（msgspec.Struct 要求无默认值的字段不能排在有默认值的之后）
    name: str
    shortName: str
    kind: str
    namespace: str
    sourceFile: str
    startLine: int
    endLine: int
    sourceText: str
    # 可选/默认字段在后
    docstring: Optional[str] = None
    attrs: list[str] = msgspec.field(default_factory=list)
    isProtected: bool = False
    isExternal: bool = False
    isDeprecated: bool = False
    deprecatedSince: Optional[date] = None


class ModuleRecord(msgspec.Struct):
    module: str
    path: str
    docstring: Optional[str] = None
    title: Optional[str] = None
    tags: list[str] = msgspec.field(default_factory=list)
    authors: list[str] = msgspec.field(default_factory=list)
    isDeprecated: bool = False
    imports: list[Import] = msgspec.field(default_factory=list)
    namespaces: list[str] = msgspec.field(default_factory=list)
    declarations: list[Declaration] = msgspec.field(default_factory=list)


class Dep(msgspec.Struct):
    name: str
    inType: bool = False
    inValue: bool = False


class ExtendsItem(msgspec.Struct):
    parent: str
    position: int


class DeprecatedBy(msgspec.Struct):
    replacement: str
    message: Optional[str] = None
    since: Optional[str] = None


class ExtractRecord(msgspec.Struct):
    name: str
    typeSignature: str
    deps: list[Dep] = msgspec.field(default_factory=list)
    # v2 结构关系边（缺省时为空/null，向后兼容旧 extract.jsonl）
    extends: list[ExtendsItem] = msgspec.field(default_factory=list)
    instantiates: Optional[str] = None
    instancePriority: Optional[int] = None
    deprecatedBy: Optional[DeprecatedBy] = None
    additiveVersion: Optional[str] = None


def module_to_json(m: ModuleRecord) -> str:
    return msgspec.json.encode(m).decode()


def module_from_json(s: str | bytes) -> ModuleRecord:
    return msgspec.json.decode(s, type=ModuleRecord)


def extract_to_json(e: ExtractRecord) -> str:
    return msgspec.json.encode(e).decode()


def extract_from_json(s: str | bytes) -> ExtractRecord:
    return msgspec.json.decode(s, type=ExtractRecord)
