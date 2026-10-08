from leanatlas.models import extract_from_json, extract_to_json

V3 = (
    '{"name":"Mathlib.A.foo","typeSignature":"∀ x, x",'
    '"deps":[{"name":"Nat","inValue":true}],"module":"Mathlib.A"}'
)
V2 = '{"name":"Mathlib.A.foo","typeSignature":"∀ x, x"}'


def test_v3_module_field_round_trips():
    rec = extract_from_json(V3)
    assert rec.module == "Mathlib.A"
    assert rec.name == "Mathlib.A.foo"
    assert extract_to_json(rec)  # encodes without error


def test_v2_record_decodes_module_none():
    assert extract_from_json(V2).module is None
