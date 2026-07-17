# mathlib_kg

把 Lean mathlib 解析 + 抽取成 Neo4j 知识图谱（v1：结构骨架 + 精确声明级依赖 DAG）。

## 它做什么

三段解耦管线，中间产物为 JSONL：

```
*.lean ──[parse_source]──► structure.jsonl ─┐
                                            ├──[load_neo4j]──► Neo4j
.olean(env) ──[Extract.lean lake exe]──► extract.jsonl ─┘
```

- **节点**：`Declaration`（含 `typeSignature` 规范类型 + `sourceText` 源码体）、`Module`、`Namespace`
- **关系**：`DEPENDS_ON`（声明级精确依赖 DAG）、`IMPORTS`（模块间）、`IN_NAMESPACE`、`SUBNAMESPACE_OF`、`DEFINED_IN`
- 外部常量（`Std`/`Batteries`/Lean 内置如 `Nat`/`Eq`）建 `isExternal:true` 占位节点，保证图完整可遍历

## 安装

```bash
cd mathlib_kg
pip install -e ".[dev]"
```

Lean 抽取工具（首次会复用已编译的 mathlib `.olean`，约数分钟设置工作区）：

```bash
cd extract && lake build extract
```

## 配置（环境变量）

| 变量 | 默认 | 说明 |
|------|------|------|
| `MATHLIB_KG_NEO4J_URI` | `bolt://localhost:7687` | |
| `MATHLIB_KG_NEO4J_USER` | （空） | |
| `MATHLIB_KG_NEO4J_PASSWORD` | （空） | |
| `MATHLIB_KG_NEO4J_DB` | `neo4j` | 社区版用默认库；KG 数据靠标签与既有数据隔离 |
| `MATHLIB_KG_MATHLIB_PATH` | `/path/to/mathlib4` | |

## 用法

```bash
export MATHLIB_KG_NEO4J_USER=neo4j MATHLIB_KG_NEO4J_PASSWORD=...

# 解析全部 Mathlib/ 源码
mathlib-kg parse --mathlib-path /path/to/mathlib4 --out structure.jsonl

# 抽取全部依赖（最贵一步；lake exe 抽取整个 mathlib 环境）
( cd extract && lake exe extract Mathlib > ../extract.jsonl )

# 装载（先建 schema，按 模块→命名空间→声明→import→依赖 顺序）
mathlib-kg load --structure structure.jsonl --extract extract.jsonl

# 查询
mathlib-kg query "MATCH (:Declaration {name:'Nat'})<-[:DEPENDS_ON*1..6]-(d) RETURN count(DISTINCT d)"

# 清空重跑
mathlib-kg drop
```

## 验收 / 测试

```bash
# 单元测试（纯 Python，无需 Neo4j/Lean）
pytest

# 含 Neo4j 的集成测试
MATHLIB_KG_NEO4J_PASSWORD=... pytest

# Lean 抽取 golden 测试
MATHLIB_KG_SKIP_LEAN=0 pytest tests/test_extract.py

# 端到端验收（Init.Data.Nat.Basic）
MATHLIB_KG_RUN_ACCEPTANCE=1 MATHLIB_KG_NEO4J_PASSWORD=... pytest tests/test_acceptance.py -v -s
```

## v1 范围与后续

v1（本包）= 地基：节点 + 命名空间树 + import 边 + 精确依赖 DAG。

后续阶段（各自独立 spec）：v2 结构关系（`EXTENDS`/`INSTANTIATES`/`DEPRECATED_BY`…）、v3 语义检索（向量嵌入）、v4 版本演化（git 历史）、v5 查询/Agent 层（MCP）。

## 已知限制（v1）

- regex 解析覆盖 ~90% 声明头；无法识别的记 warning 不中断。
- `private` 声明（`_private....` 前缀）与匿名辅助常量：匿名项 delab 失败时兜底为原始 Expr 表示，不中断。
- **抽取范围 = 模块的传递 import 闭包**：抽取单个模块（如 `Mathlib.Algebra.Quandle`）只得到该模块及其依赖闭包，不含未被它 import 的模块（如 NumberTheory）。要装载完整 mathlib 图，必须抽取聚合模块 `Mathlib`（它在 `Mathlib.lean` 中 import 全部子模块）。
