"""列角色识别、人员主数据对齐。"""

from __future__ import annotations

from .schema import COLUMN_ROLES, NULL_CELL


def normalize_cell(value: str) -> str:
    return (value or "").strip()


def is_null(value: str) -> bool:
    return normalize_cell(value) in NULL_CELL


def role_of_header(header: str) -> str | None:
    key = header.strip().lower().replace(" ", "")
    for role, aliases in COLUMN_ROLES.items():
        folded = {a.lower().replace(" ", "") for a in aliases}
        if header.strip() in aliases or key in folded:
            return role
    return None


def map_headers(headers: list[str]) -> dict[str, int]:
    """表头 → 角色下标；同一角色只保留首次命中。"""
    out: dict[str, int] = {}
    for i, header in enumerate(headers):
        role = role_of_header(header)
        if role and role not in out:
            out[role] = i
    return out


def cell(row: list[str], roles: dict[str, int], role: str) -> str:
    idx = roles.get(role)
    if idx is None or idx >= len(row):
        return ""
    return normalize_cell(row[idx])


def _attr(obj: object, key: str) -> str:
    if isinstance(obj, dict):
        return str(obj.get(key) or "")
    return str(getattr(obj, key, "") or "")


class IdentityIndex:
    """以通讯录为主数据：姓名 / 工号互查。"""

    def __init__(self, people: list) -> None:
        self.by_name: dict[str, str] = {}
        self.by_emp: dict[str, str] = {}
        for p in people:
            name = _attr(p, "name")
            emp = _attr(p, "emp_id")
            if name:
                self.by_name[name] = name
            if emp and name:
                self.by_emp[emp.upper()] = name

    def resolve(self, raw: str) -> str | None:
        text = normalize_cell(raw)
        if is_null(text):
            return None
        if text in self.by_name:
            return self.by_name[text]
        emp = self.by_emp.get(text.upper())
        if emp:
            return emp
        hits = [n for n in self.by_name if n and n in text]
        if hits:
            return max(hits, key=len)
        return text

    def link_in_question(self, question: str, extra: list[str] | None = None) -> str | None:
        names = list(self.by_name) + list(self.by_emp) + list(extra or [])
        hits = [n for n in names if n and n in question]
        if not hits:
            return None
        best = max(hits, key=len)
        return self.resolve(best) or best
