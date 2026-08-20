"""图本体：标签、关系、列角色同义词。查询只允许这些类型，禁止拼用户字符串当 label。"""

from __future__ import annotations

from typing import Literal

REL_REPORTS_TO = "REPORTS_TO"
REL_DEPENDS_ON = "DEPENDS_ON"
REL_NEXT = "NEXT_STEP"

ALLOWED_RELS = frozenset({REL_REPORTS_TO, REL_DEPENDS_ON, REL_NEXT})

Pattern = Literal["reports_to", "depends_on", "approval_chain", "neighborhood"]

NULL_CELL = frozenset({"", "—", "-", "–", "无", "n/a", "N/A", "none", "null"})

# CSV / 表头 → 语义角色（生产里这张表会进配置中心；这里是本体层，不是某一篇文档的列名）
COLUMN_ROLES: dict[str, frozenset[str]] = {
    "person_name": frozenset({"姓名", "员工", "员工姓名", "成员", "name", "人员"}),
    "emp_id": frozenset({"工号", "员工编号", "工号id", "emp_id", "employee_id"}),
    "dept": frozenset({"部门", "dept", "department"}),
    "title": frozenset({"岗位", "职位", "title", "职务"}),
    "manager": frozenset({"直属上级", "上级", "汇报对象", "经理", "manager", "reports_to"}),
    "service": frozenset({"服务", "系统", "应用", "组件", "service", "system"}),
    "depends": frozenset({"直接依赖", "依赖", "depends", "下游", "调用"}),
    "seq": frozenset({"序号", "顺序", "步骤号", "seq", "step_no"}),
    "step": frozenset({"环节", "步骤", "节点", "step"}),
    "actor": frozenset({"角色或人员", "审批人", "责任人", "角色", "actor", "owner"}),
}

# 问句 → 模式（降级：LLM 规划失败时用本体词典，不绑死某一条审批流程名）
PATTERN_LEXICON: dict[Pattern, frozenset[str]] = {
    "reports_to": frozenset({"上级", "汇报", "下属", "隔级", "经理是谁", "向谁汇报"}),
    "depends_on": frozenset({"依赖", "调用", "下游", "依赖链"}),
    "approval_chain": frozenset({"审批链", "审批环节", "审批流程", "环节顺序"}),
}

HOP2_HINTS = frozenset({"隔级", "上级的上级", "两级", "间接", "2跳", "两跳"})

SCHEMA_CARD = """
节点标签：Person(name, emp_id, dept, title), Service(name), Step(id, seq, name, actor, process), SourceDoc(path, file_hash)
关系类型（仅允许）：
- (Person)-[:REPORTS_TO]->(Person)  直属汇报，多跳用变长 *1..n
- (Service)-[:DEPENDS_ON]->(Service) 直接依赖
- (Step)-[:NEXT]->(Step) 同一 process 内的下一审批环节
"""
