/-
  Extract.lean — Extract each declaration's dependencies and pretty-printed type from a
  compiled Lean environment; emit JSONL to stdout.
  Usage (from the extract/ directory): lake exe extract [ModuleName] > extract.jsonl
  Defaults to extracting `Mathlib` (including all transitive imports). Reuses mathlib's
  precompiled .olean files.

  v2: each record additionally carries 5 structural relation fields:
    - extends          : [{parent, position}]   EXTENDS (parents a structure inherits from)
    - instantiates     : String | null          INSTANTIATES (head constant of the instance's type)
    - instancePriority : Number | null          priority of that instance
    - deprecatedBy     : {replacement, message, since} | null  DEPRECATED_BY
    - additiveVersion  : String | null          HAS_ADDITIVE_VERSION (to_additive target)

  v3: each record additionally carries `module` (defining module name, compiler
    truth; null for main-module constants and the minimal fallback records).
-/
import Lean
import Lean.Data.Json
import Mathlib.Tactic.ToAdditive         -- provides Mathlib.Tactic.ToAdditive.translations

open Lean

def main (args : List String) : IO UInt32 := do
  Lean.initSearchPath (← Lean.findSysroot)
  let modName := (args.head?.getD "Mathlib").toName
  -- loadExts := true is required to replay environment extensions
  -- (instance table, attribute tables, to_additive, etc.);
  -- otherwise isInstanceCore / deprecatedAttr / translations all come back empty.
  unsafe Lean.enableInitializersExecution
  let env ← importModules #[{ module := modName }] Options.empty (loadExts := true)
  let lctx := LocalContext.empty
  let mctx : MetavarContext := {}
  -- Enumerate all constants via the kernel env (the elaborator's env.constants is only a
  -- working subset)
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
      -- Dependencies occurring in the type: inType=true
      for d in typeDeps do
        if d = name then continue
        if seen.contains d then continue
        seen := seen.insert d
        entries := entries.push <|
          Json.mkObj [("name", Json.str d.toString),
                       ("inType", Json.bool true),
                       ("inValue", Json.bool (valueDeps.contains d))]
      -- Dependencies occurring only in the value: inType=false, inValue=true
      for d in valueDeps do
        if d = name then continue
        if seen.contains d then continue
        seen := seen.insert d
        entries := entries.push <|
          Json.mkObj [("name", Json.str d.toString),
                       ("inType", Json.bool false),
                       ("inValue", Json.bool true)]
      -- delab may throw on anonymous/auxiliary constants; fall back to the raw Expr repr
      let typeSig ← try
        let fmt ← PrettyPrinter.ppExprLegacy env mctx lctx Options.empty ci.type
        pure (toString fmt)
      catch _ =>
        pure (toString (repr ci.type))

      -- v2 relation edge fields
      -- EXTENDS: structures/classes only
      let extendsArr : Json :=
        if Lean.isStructure env name then
          let parents := Lean.getStructureParentInfo env name
          let arr : Array Json := parents.mapIdx fun i pi =>
            -- Parent structure name: v4.30.0 StructureParentInfo.structName : Name
            let pname : Name := pi.structName
            Json.mkObj [("parent", Json.str pname.toString), ("position", Json.num i)]
          Json.arr arr
        else Json.arr #[]
      -- INSTANTIATES: head constant of the instance's type; also fetch its priority
      let instState := Lean.Meta.instanceExtension.getState env
      let isInst : Bool := Lean.Meta.isInstanceCore env name
      let instPair : Json × Json :=
        if isInst then
          -- strip Pi binders (instance types are usually ∀ binders..., ClassApp)
          -- getAppFn only strips app nodes, it does not descend through forallE/mdata,
          -- so strip those layers manually first
          let rec stripPi (e : Expr) : Expr :=
            match e with
            | .forallE _ _ body _ => stripPi body
            | .mdata _ b => stripPi b
            | _ => e
          match (stripPi ci.type).getAppFn.constName? with
          | some head =>
            if Lean.isStructure env head then
              let prio : Option Nat := instState.instanceNames.find? name |>.map (·.priority)
              (Json.str head.toString, prio.map Json.num |>.getD Json.null)
            else (Json.null, Json.null)
          | none => (Json.null, Json.null)
        else (Json.null, Json.null)
      let instName : Json := instPair.1
      let instPrio : Json := instPair.2
      -- DEPRECATED_BY: read the deprecated attribute table
      let depObj : Json :=
        match Lean.Linter.deprecatedAttr.getParam? env name with
        | some d =>
          Json.mkObj [
            ("replacement", d.newName?.map (fun n => Json.str n.toString) |>.getD Json.null),
            ("message", d.text?.map Json.str |>.getD Json.null),
            ("since", d.since?.map Json.str |>.getD Json.null)]
        | none => Json.null
      -- HAS_ADDITIVE_VERSION: read the to_additive translation table
      let addName : Json :=
        match Mathlib.Tactic.ToAdditive.translations.find? env name with
        | some info => Json.str info.translation.toString
        | none => Json.null

      -- v2.5 fields/constructors: only type constants (.inductInfo) emit constructors;
      -- structures additionally emit flattened fields.
      -- Step 2 verification (v4.30.0 sources + empirical checks):
      --   * getStructureFieldsFlattened env n : Array Name — returns SHORT single-component
      --     names (e.g. `#[toD1, d1, d2]`: the toParent coercion + flattened inherited fields
      --     + own fields).
      --   * The projection name of an inherited field is NOT `child.field` — Lean reuses the
      --     parent structure's projection (e.g. `d1` of `D2 extends D1` resolves to the actual
      --     projection `D1.d1`, not a child-synthesized `D2.d1`).
      --     So first use findField? to locate the structure owning the field, then take its real
      --     projFn; for a subobject field (e.g. `toD1`), findField? directly returns the child
      --     structure, whose projFn is `D2.toD1`.
      --   * InductiveVal.ctors : List Name — already holds FULLY-QUALIFIED constructor names;
      --     use as-is (call toArray first to pair with mapIdx).
      let ctorsArr : Json :=
        match ci with
        | .inductInfo iv =>
          -- iv.ctors : List Name; toArray then mapIdx so it is an Array Json like fieldsArr
          Json.arr (iv.ctors.toArray.mapIdx fun i n =>
            Json.mkObj [("name", Json.str n.toString), ("position", Json.num i)])
        | _ => Json.arr #[]
      let fieldsArr : Json :=
        match ci with
        | .inductInfo _ =>
          if Lean.isStructure env name then
            -- Step 2 empirical finding: getStructureFieldsFlattened returns SHORT names of the
            -- flattened fields, but the projection name of an inherited field is not always
            -- `child.field` — if the field is actually owned by a parent structure, Lean reuses
            -- the parent's projection (e.g. `d1` of `D2 extends D1` resolves to the actual
            -- projection `D1.d1`, not a child-synthesized `D2.d1`). Subobject fields (e.g.
            -- `toD1`) use the child structure's own projection.
            -- So for each flattened field, locate its owning structure via findField?, then
            -- take the real projFn.
            let fs := Lean.getStructureFieldsFlattened env name
            Json.arr (fs.mapIdx fun i f =>
              let owner : Name := Lean.findField? env name f |>.getD name
              let fullName : Name :=
                Lean.getProjFnForField? env owner f |>.getD (Name.mkStr name f.toString)
              Json.mkObj [("name", Json.str fullName.toString), ("position", Json.num i)])
          else Json.arr #[]
        | _ => Json.arr #[]

      -- v3: defining module of the constant — compiler truth via the module
      -- index. This covers auto-generated instances and _private declarations
      -- that regex source parsing cannot see (the P1.5 join-basis fix).
      let moduleJson : Json :=
        match env.getModuleIdxFor? name with
        | some idx =>
          match env.header.moduleNames[idx]? with
          | some m => Json.str m.toString
          | none => Json.null
        | none => Json.null

      let obj := Json.mkObj [
        ("name", Json.str name.toString),
        ("module", moduleJson),
        ("typeSignature", Json.str typeSig),
        ("deps", Json.arr entries),
        ("extends", extendsArr),
        ("instantiates", instName),
        ("instancePriority", instPrio),
        ("deprecatedBy", depObj),
        ("additiveVersion", addName),
        ("fields", fieldsArr),
        ("constructors", ctorsArr)]
      IO.println obj.compress
    catch _ =>
      -- Rare: processing the whole record failed; emit a minimal record so no constant is
      -- lost and the run is not interrupted
      IO.println (Json.mkObj [("name", Json.str name.toString),
                              ("typeSignature", Json.str ""),
                              ("deps", Json.arr #[])]).compress
  return 0
