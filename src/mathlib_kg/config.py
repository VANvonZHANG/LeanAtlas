"""Configuration via environment variables with sensible defaults."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_db: str
    mathlib_path: str


def get_config() -> Config:
    return Config(
        neo4j_uri=os.environ.get("MATHLIB_KG_NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.environ.get("MATHLIB_KG_NEO4J_USER", ""),
        neo4j_password=os.environ.get("MATHLIB_KG_NEO4J_PASSWORD", ""),
        neo4j_db=os.environ.get("MATHLIB_KG_NEO4J_DB", "neo4j"),
        mathlib_path=os.environ.get(
            "MATHLIB_KG_MATHLIB_PATH", "/path/to/mathlib4"
        ),
    )
