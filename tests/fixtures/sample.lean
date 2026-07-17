/-
Copyright (c) 2020 Kyle Miller. All rights reserved.
Released under Apache 2.0 license as described in the file LICENSE.
Authors: Kyle Miller, Mario Carneiro
-/
module

public import Mathlib.Data.Set.Basic
import Mathlib.Algebra.Group.Basic

/-!
# Racks and Quandles

This file defines racks and quandles.

## Tags

rack, quandle
-/

class Shelf (α : Type u) where
  act : α → α → α
