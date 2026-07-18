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

def newB : Nat := 0

/-- deprecated，测 DEPRECATED_BY 边 -/
@[deprecated StructEdgesFixture.newB "use newB instead" (since := "2024-01-01")]
def oldB : Nat := 0

/-- to_additive，测 HAS_ADDITIVE_VERSION 边 -/
@[to_additive addFoo]
def foo {α : Type} [Mul α] (x y : α) : α := x * y

end StructEdgesFixture
