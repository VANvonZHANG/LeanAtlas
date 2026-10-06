from leanatlas.config import get_config


def test_config_defaults(monkeypatch):
    for k in (
        "LEANATLAS_NEO4J_USER",
        "LEANATLAS_NEO4J_PASSWORD",
        "LEANATLAS_NEO4J_DB",
        "LEANATLAS_MATHLIB_PATH",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = get_config()
    assert cfg.neo4j_uri == "bolt://localhost:7687"
    assert cfg.neo4j_db == "neo4j"  # Community Edition uses the default database
    assert cfg.mathlib_path is None
    assert cfg.neo4j_user == ""
    assert cfg.neo4j_password == ""


def test_config_env_override(monkeypatch):
    monkeypatch.setenv("LEANATLAS_NEO4J_USER", "neo4j")
    monkeypatch.setenv("LEANATLAS_NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("LEANATLAS_NEO4J_DB", "leanatlas_test")
    monkeypatch.setenv("LEANATLAS_MATHLIB_PATH", "/tmp/ml")
    cfg = get_config()
    assert cfg.neo4j_user == "neo4j"
    assert cfg.neo4j_password == "secret"
    assert cfg.neo4j_db == "leanatlas_test"
    assert cfg.mathlib_path == "/tmp/ml"
