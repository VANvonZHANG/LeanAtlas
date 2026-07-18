/-
  Extract.lean — 从已编译的 Lean 环境抽取每条声明的依赖与规范类型，输出 JSONL 到 stdout。
  用法（在 extract/ 目录）: lake exe extract [ModuleName] > extract.jsonl
  默认抽取 `Mathlib`（含其全部传递 import）。复用 mathlib 已编译的 .olean。

  v2：每条记录额外携带 5 个结构关系字段：
    - extends          : [{parent, position}]   EXTENDS（结构体继承的父类）
    - instantiates     : String | null          INSTANTIATES（instance 头常量）
    - instancePriority : Number | null          该 instance 的优先级
    - deprecatedBy     : {replacement, message, since} | null  DEPRECATED_BY
    - additiveVersion  : String | null          HAS_ADDITIVE_VERSION（to_additive 目标）
-/
import Lean
import Lean.Data.Json
import Mathlib.Tactic.ToAdditive         -- 提供 Mathlib.Tactic.ToAdditive.translations

open Lean

def main (args : List String) : IO UInt32 := do
  Lean.initSearchPath (← Lean.findSysroot)
  let modName := (args.head?.getD "Mathlib").toName
  -- loadExts := true 才会重放环境扩展（实例表/属性表/to_additive 等），
  -- 否则 isInstanceCore / deprecatedAttr / translations 等全部读不到。
  unsafe Lean.enableInitializersExecution
  let env ← importModules #[{ module := modName }] Options.empty (loadExts := true)
  let lctx := LocalContext.empty
  let mctx : MetavarContext := {}
  -- 用 kernel env 枚举全部常量（elaborator 的 env.constants 只是工作子集）
  let kenv := env.toKernelEnv
  let consts := kenv.constants.fold (init := []) (fun acc name ci => (name, ci) :: acc)
  IO.eprintln s!"[extract] const count: {consts.length}"
  for (name, ci) in consts do
    try
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
      -- delab 对匿名/辅助常量可能抛异常，兜底用原始 Expr 表示
      let typeSig ← try
        let fmt ← PrettyPrinter.ppExprLegacy env mctx lctx Options.empty ci.type
        pure (toString fmt)
      catch _ =>
        pure (toString (repr ci.type))

      -- v2 关系边字段
      -- EXTENDS：仅 structure/class
      let extendsArr : Json :=
        if Lean.isStructure env name then
          let parents := Lean.getStructureParentInfo env name
          let arr : Array Json := parents.mapIdx fun i pi =>
            -- 父结构名：v4.30.0 StructureParentInfo.structName : Name
            let pname : Name := pi.structName
            Json.mkObj [("parent", Json.str pname.toString), ("position", Json.num i)]
          Json.arr arr
        else Json.arr #[]
      -- INSTANTIATES：instance 的类型头常量；同时取优先级
      let instState := Lean.Meta.instanceExtension.getState env
      let isInst : Bool := Lean.Meta.isInstanceCore env name
      let instPair : Json × Json :=
        if isInst then
          match ci.type.getAppFn.constName? with
          | some head =>
            if Lean.isStructure env head then
              let prio : Option Nat := instState.instanceNames.find? name |>.map (·.priority)
              (Json.str head.toString, prio.map Json.num |>.getD Json.null)
            else (Json.null, Json.null)
          | none => (Json.null, Json.null)
        else (Json.null, Json.null)
      let instName : Json := instPair.1
      let instPrio : Json := instPair.2
      -- DEPRECATED_BY：读 deprecated 属性表
      let depObj : Json :=
        match Lean.Linter.deprecatedAttr.getParam? env name with
        | some d =>
          Json.mkObj [
            ("replacement", d.newName?.map (fun n => Json.str n.toString) |>.getD Json.null),
            ("message", d.text?.map Json.str |>.getD Json.null),
            ("since", d.since?.map Json.str |>.getD Json.null)]
        | none => Json.null
      -- HAS_ADDITIVE_VERSION：读 to_additive 翻译表
      let addName : Json :=
        match Mathlib.Tactic.ToAdditive.translations.find? env name with
        | some info => Json.str info.translation.toString
        | none => Json.null

      let obj := Json.mkObj [
        ("name", Json.str name.toString),
        ("typeSignature", Json.str typeSig),
        ("deps", Json.arr entries),
        ("extends", extendsArr),
        ("instantiates", instName),
        ("instancePriority", instPrio),
        ("deprecatedBy", depObj),
        ("additiveVersion", addName)]
      IO.println obj.compress
    catch _ =>
      -- 罕见：整条处理失败，输出最小记录，保证不丢常量、不中断
      IO.println (Json.mkObj [("name", Json.str name.toString),
                              ("typeSignature", Json.str ""),
                              ("deps", Json.arr #[])]).compress
  return 0
