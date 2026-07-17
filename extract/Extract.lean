/-
  Extract.lean — 从已编译的 Lean 环境抽取每条声明的依赖与规范类型，输出 JSONL 到 stdout。
  用法（在 extract/ 目录）: lake exe extract [ModuleName] > extract.jsonl
  默认抽取 `Mathlib`（含其全部传递 import）。复用 mathlib 已编译的 .olean。
-/
import Lean
import Lean.Data.Json

open Lean

def main (args : List String) : IO UInt32 := do
  Lean.initSearchPath (← Lean.findSysroot)
  let modName := (args.head?.getD "Mathlib").toName
  let env ← importModules #[{ module := modName }] Options.empty
  let lctx := LocalContext.empty
  let mctx : MetavarContext := {}
  -- 用 kernel env 枚举全部常量（elaborator 的 env.constants 只是工作子集）
  let kenv := env.toKernelEnv
  let consts := kenv.constants.fold (init := []) (fun acc name ci => (name, ci) :: acc)
  IO.eprintln s!"[extract] const count: {consts.length}"
  for (name, ci) in consts do
    let typeDeps := ci.type.getUsedConstants
    let valueDeps :=
      ci.value? (allowOpaque := true) |>.map (·.getUsedConstants) |>.getD #[]
    let mut seen : NameSet := {}
    let mut entries : Array Json := #[]
    -- 类型中的依赖：inType=true
    for d in typeDeps do
      if d = name then continue
      if seen.contains d then continue
      seen := seen.insert d
      entries := entries.push <|
        Json.mkObj [("name", Json.str d.toString),
                     ("inType", Json.bool true),
                     ("inValue", Json.bool (valueDeps.contains d))]
    -- 仅出现在值里的依赖：inType=false, inValue=true
    for d in valueDeps do
      if d = name then continue
      if seen.contains d then continue
      seen := seen.insert d
      entries := entries.push <|
        Json.mkObj [("name", Json.str d.toString),
                     ("inType", Json.bool false),
                     ("inValue", Json.bool true)]
    let fmt ← PrettyPrinter.ppExprLegacy env mctx lctx Options.empty ci.type
    let obj := Json.mkObj [("name", Json.str name.toString),
                            ("typeSignature", Json.str (toString fmt)),
                            ("deps", Json.arr entries)]
    IO.println obj.compress
  return 0
