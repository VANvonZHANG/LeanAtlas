/-
  StructEdgesFixture.lean — v2 关系边抽取的测试 fixture。
  覆盖 EXTENDS / INSTANTIATES / DEPRECATED_BY / HAS_ADDITIVE_VERSION 四种关系。
-/
import Mathlib.Algebra.Group.Basic

namespace StructEdgesFixture

/-- 基类，供 extends 测试 -/
class A where
  a : Nat

/-- extends A，测 EXTENDS 边 -/
class B extends A where
  b : Nat

/-- instance，测 INSTANTIATES 边 -/
instance instB : B where
  a := 0
  b := 0

/-- 参数化 instance：类型为 `∀ (α : Type), C α`，回归 INSTANTIATES Pi-binder bug。
    旧代码对 `ci.type.getAppFn` 不会下穿 forallE，导致 head 取不到 → instantiates:null。 -/
class C (α : Type) where
  c : α → α

instance instC (α : Type) : C α where
  c := fun x => x

def newB : Nat := 0

/-- deprecated，测 DEPRECATED_BY 边 -/
@[deprecated StructEdgesFixture.newB "use newB instead" (since := "2024-01-01")]
def oldB : Nat := 0

/-- to_additive，测 HAS_ADDITIVE_VERSION 边 -/
@[to_additive addFoo]
def foo {α : Type} [Mul α] (x y : α) : α := x * y

/-- v2.5：基类，供扁平字段测试 -/
class D1 where
  d1 : Nat

/-- v2.5：extends D1，测 HAS_FIELD 扁平（D2 应含继承合成投影 D2.d1 + 自有 D2.d2；
  强转 D2.toD1 是否计入由 getStructureFieldsFlattened 决定，见 Step 2）。 -/
class D2 extends D1 where
  d2 : Nat

/-- v2.5：归纳类型，测 HAS_CONSTRUCTOR（多构造子 + position）。 -/
inductive Foo
  | c1 : Foo
  | c2 : Nat → Foo

end StructEdgesFixture
