"""Infer what an action can prove from tool metadata and arguments."""

from __future__ import annotations

import re

SCHEMA_WORDS = ("schema", "table", "column", "field", "โครงสร้าง", "คอลัมน์")
QUERY_WORDS = ("query", "sql", "aggregate", "metric", "จำนวน", "อัตรา", "ค่าเฉลี่ย")


def infer_action_capabilities(tool: str, arguments: dict | None = None) -> set[str]:
    name = tool.lower()
    sql = re.sub(r"\s+", " ", str((arguments or {}).get("query", ""))).lower()
    capabilities: set[str] = set()
    if any(token in name for token in ("schema", "table", "column", "describe", "database_context")):
        capabilities.update(("schema_presence", "schema_absence", "sample_shape"))
    if any(token in name for token in ("query", "sql", "execute")):
        capabilities.update(("query_result", "grouped_metric", "comparison", "proportion"))
        if any(token in sql for token in ("information_schema", "sys.columns", "sys.tables")):
            capabilities.update(("schema_presence", "schema_absence"))
    return capabilities


def required_step_capability(step_description: str) -> str | None:
    step = step_description.lower()
    if any(word in step for word in SCHEMA_WORDS):
        return "schema_presence"
    if any(word in step for word in QUERY_WORDS):
        return "query_result"
    return None
