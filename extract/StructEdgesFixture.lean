/-
  StructEdgesFixture.lean — test fixture for v2 relation edge extraction.
  Covers the four relations: EXTENDS / INSTANTIATES / DEPRECATED_BY / HAS_ADDITIVE_VERSION.
-/
import Mathlib.Algebra.Group.Basic

namespace StructEdgesFixture

/-- Base class for the extends test -/
class A where
  a : Nat

/-- extends A, to test the EXTENDS edge -/
class B extends A where
  b : Nat

/-- instance, to test the INSTANTIATES edge -/
instance instB : B where
  a := 0
  b := 0

/-- Parameterized instance: type is `∀ (α : Type), C α`; regression test for the INSTANTIATES
    Pi-binder bug. The old code's `ci.type.getAppFn` did not descend through forallE, so the
    head constant was missed → instantiates:null. -/
class C (α : Type) where
  c : α → α

instance instC (α : Type) : C α where
  c := fun x => x

def newB : Nat := 0

/-- deprecated, to test the DEPRECATED_BY edge -/
@[deprecated StructEdgesFixture.newB "use newB instead" (since := "2024-01-01")]
def oldB : Nat := 0

/-- to_additive, to test the HAS_ADDITIVE_VERSION edge -/
@[to_additive addFoo]
def foo {α : Type} [Mul α] (x y : α) : α := x * y

/-- v2.5: base class for the flattened-field test -/
class D1 where
  d1 : Nat

/-- v2.5: extends D1, to test HAS_FIELD flattening (D2 should contain the inherited synthesized
  projection D2.d1 + its own D2.d2; whether the coercion D2.toD1 is included is decided by
  getStructureFieldsFlattened, see Step 2). -/
class D2 extends D1 where
  d2 : Nat

/-- v2.5: inductive type, to test HAS_CONSTRUCTOR (multiple constructors + position). -/
inductive Foo
  | c1 : Foo
  | c2 : Nat → Foo

end StructEdgesFixture
