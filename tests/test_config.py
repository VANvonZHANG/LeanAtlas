from leanatlas.config import get_config


def test_config_defaults(monkeypatch):
    for k in (
        "MATHLIB_KG_NEO4J_USER",
        "MATHLIB_KG_NEO4J_PASSWORD",
        "MATHLIB_KG_NEO4J_DB",
        "MATHLIB_KG_MATHLIB_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = get_config()
    assert cfg.neo4j_uri == "bolt://localhost:7687"
    assert cfg.neo4j_db == "neo4j"  # Community Edition uses the default database
    assert cfg.mathlib_path == "/path/to/mathlib4"
    assert cfg.neo4j_user == ""
    assert cfg.neo4j_password == ""


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("MATHLIB_KG_NEO4J_USER", "neo4j")
    monkeypatch.setenv("MATHLIB_KG_NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("MATHLIB_KG_NEO4J_DB", "mathlibkg_test")
    monkeypatch.setenv("MATHLIB_KG_MATHLIB_PATH", "/tmp/ml")
    cfg = get_config()
    assert cfg.neo4j_user == "neo4j"
    assert cfg.neo4j_password == "secret"
    assert cfg.neo4j_db == "mathlibkg_test"
    assert cfg.mathlib_path == "/tmp/ml"
