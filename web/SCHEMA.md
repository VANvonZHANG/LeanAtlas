# web/data.json 契约（schemaVersion: 1）

生成：`mathlib-kg layout --structure structure.jsonl --out web/data.json`
（数据为**传递约简后**的边；节点顺序 = 拓扑序，数组下标即节点 id。）

```jsonc
{
  "schemaVersion": 1,
  "meta": {
    "version": "mathlib git describe（取不到为 \"unknown\"）",
    "generatedAt": "ISO8601",
    "scope": "mathlib",
    "stats": {
      "modules": 0,               // Mathlib.* 存活模块数（已删根伞、排除 Archive/Counterexamples）
      "edgesDirect": 0,           // 直接 import 边（内部、去重）
      "edgesReduced": 0,          // 传递约简后导出（= edges 数组长度）
      "skippedExternalImports": 0,// 指向 Lean core/Std/Batteries 等外部模块的 import 次数
      "skippedBadLines": 0,       // structure.jsonl 损坏行数
      "unmatchedTopicModules": 0  // 落入 _default 带的模块数
    }
  },
  "topics": [                     // 含 _default；顺序 = 匹配优先级
    { "id": "Algebra", "label": "Algebra", "labelZh": "代数", "y": 100.0, "color": "#ffff00" }
  ],
  "nodes": [                      // 数组下标 = 节点 id（隐式）；顺序 = 拓扑序（依赖在前）
    { "name": "Mathlib.X.Y", "topic": "Algebra",
      "x": 12.93, "y": 100.0, "r": 2.09, "color": "#ffff00",
      "declCount": 35, "closureSize": 35, "isDeprecated": false,
      "title": "…", "docstring": "…" }      // title/docstring 可为 null；docstring ≤1000 字符
  ],
  "edges": [[3, 0], [3, 1]]       // [dep_idx, importer_idx]：j import i；已传递约简
}
```

字段语义速查：
- `x` = |传递依赖闭包|^0.72（左→右 = 从地基到塔尖；零闭包模块散布在 -0..-9 十列）
- `y` = topic 泳道（带值 + 列内同 topic 前驱平均 + 确定性锯齿槽位）
- `r` = 0.2 + 3·√(归一化 PageRank)（面积 ∝ 地基性）
- `closureSize` = 传递依赖数（未来 z 轴/抽象层级原料）
- 边向与 `lake exe graph` dot 一致：依赖 → 被依赖
