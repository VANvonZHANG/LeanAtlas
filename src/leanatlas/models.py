"""Data structures for structure.jsonl and extract.jsonl records."""
from datetime import date
from typing import Optional

import msgspec


class Import(msgspec.Struct):
    name: str
    isPublic: bool = False
    isDeprecated: bool = False


class Declaration(msgspec.Struct):
    # Required fields first (msgspec.Struct forbids fields without defaults
    # after fields with defaults)
    name: str
    shortName: str
    kind: str
    namespace: str
    sourceFile: str
    startLine: int
    endLine: int
    sourceText: str
    # Optional/defaulted fields after
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


class FieldItem(msgspec.Struct):
    name: str
    position: int


class CtorItem(msgspec.Struct):
    name: str
    position: int


class ExtractRecord(msgspec.Struct):
    name: str
    typeSignature: str
    deps: list[Dep] = msgspec.field(default_factory=list)
    # v2 structural relationship edges (empty/null by default, backward
    # compatible with old extract.jsonl)
    extends: list[ExtendsItem] = msgspec.field(default_factory=list)
    instantiates: Optional[str] = None
    instancePriority: Optional[int] = None
    deprecatedBy: Optional[DeprecatedBy] = None
    additiveVersion: Optional[str] = None
    # v2.5 fields/constructors (empty lists by default, backward compatible)
    fields: list[FieldItem] = msgspec.field(default_factory=list)
    constructors: list[CtorItem] = msgspec.field(default_factory=list)


def module_to_json(m: ModuleRecord) -> str:
    return msgspec.json.encode(m).decode()


def module_from_json(s: str | bytes) -> ModuleRecord:
    return msgspec.json.decode(s, type=ModuleRecord)


def extract_to_json(e: ExtractRecord) -> str:
    return msgspec.json.encode(e).decode()


def extract_from_json(s: str | bytes) -> ExtractRecord:
    return msgspec.json.decode(s, type=ExtractRecord)
