"""
MOD-014: RiskAssessor — Fix plan risk assessment engine.
@author sub_agent_software_developer
@module MOD-014
@implements IFC-014-01
@depends None
@covers REQ-FUNC-012, REQ-NFUNC-003
@fixes D-003: Changed str(entry["risk_level"]) to entry["risk_level"].value for deterministic RiskLevel enum string conversion
"""

import re
from typing import Any

from src.models.enums import RiskLevel
from src.models.fix_plan import FixPlan, RiskAssessment


# ────────────────────────────────────────────────────
# 高风险操作模式定义（module_design.md MOD-014 表）
# ────────────────────────────────────────────────────

HIGH_RISK_PATTERNS: list[dict[str, Any]] = [
    {
        "pattern": re.compile(r"\bshutdown\b", re.IGNORECASE),
        "name": "端口 shutdown",
        "risk_level": RiskLevel.HIGH,
    },
    {
        "pattern": re.compile(r"\bno\s+shutdown\b", re.IGNORECASE),
        "name": "端口 no shutdown",
        "risk_level": RiskLevel.HIGH,
    },
    {
        "pattern": re.compile(r"\bno\s+vlan\b", re.IGNORECASE),
        "name": "VLAN 删除",
        "risk_level": RiskLevel.CRITICAL,
    },
    {
        "pattern": re.compile(r"\breload\b|\breboot\b", re.IGNORECASE),
        "name": "设备重启",
        "risk_level": RiskLevel.CRITICAL,
    },
    {
        "pattern": re.compile(r"\brouter\s+ospf\b|\brouter\s+bgp\b", re.IGNORECASE),
        "name": "路由协议变更",
        "risk_level": RiskLevel.HIGH,
    },
    {
        "pattern": re.compile(r"\bspanning-tree\b", re.IGNORECASE),
        "name": "spanning-tree 修改",
        "risk_level": RiskLevel.MEDIUM,
    },
    {
        "pattern": re.compile(r"\bwrite\s+memory\b|\bcopy\s+running\b", re.IGNORECASE),
        "name": "配置写存",
        "risk_level": RiskLevel.LOW,
    },
]


class RiskAssessor:
    """
    修复方案风险评估引擎（纯规则匹配）。
    实现 IFC-014-01: assess(fix_plan: FixPlan) → RiskAssessment
    """

    # 风险等级优先级排序（用于取最高风险）
    _RISK_ORDER: dict[str, int] = {
        RiskLevel.LOW: 0,
        RiskLevel.MEDIUM: 1,
        RiskLevel.HIGH: 2,
        RiskLevel.CRITICAL: 3,
    }

    # ── IFC-014-01: assess ──────────────────────────────────

    def assess(self, fix_plan: FixPlan) -> RiskAssessment:
        """
        评估修复方案的风险等级。
        检查 commands 列表中的每条命令，匹配高风险操作模式。

        need_human_approval 判定规则:
          - risk_level in ["HIGH", "CRITICAL"] → true
          - risk_level == "MEDIUM" 且包含多条修改命令 → true
          - risk_level == "LOW" → false
        """
        highest_risk: str = RiskLevel.LOW
        risk_reasons: list[str] = []
        matched_patterns: list[str] = []

        for command in fix_plan.commands:
            for entry in HIGH_RISK_PATTERNS:
                if entry["pattern"].search(command):
                    risk_level_str = entry["risk_level"].value
                    matched_patterns.append(entry["name"])
                    risk_reasons.append(f"命令 '{command}' 匹配高风险模式: {entry['name']}")

                    # 取最高风险等级
                    if self._RISK_ORDER.get(risk_level_str, 0) > self._RISK_ORDER.get(highest_risk, 0):
                        highest_risk = risk_level_str

        # 检查 fix_plan 中的 risk_hints
        for hint in fix_plan.risk_hints:
            risk_reasons.append(f"模板提示: {hint}")

        # need_human_approval 判定
        need_approval = self._determine_need_approval(highest_risk, len(fix_plan.commands), matched_patterns)

        return RiskAssessment(
            risk_level=highest_risk,
            need_human_approval=need_approval,
            risk_reasons=risk_reasons if risk_reasons else ["无明显高风险操作"],
            matched_high_risk_patterns=list(set(matched_patterns)),
        )

    # ── 内部辅助 ────────────────────────────────────────────

    def _determine_need_approval(
        self, highest_risk: str, command_count: int, matched_patterns: list[str]
    ) -> bool:
        """
        判定是否需要人工审批:
          - HIGH / CRITICAL → true (REQ-NFUNC-003)
          - MEDIUM + (多条修改命令 或 多个匹配模式) → true
          - LOW → false
        """
        if highest_risk in (RiskLevel.CRITICAL, RiskLevel.HIGH):
            return True

        if highest_risk == RiskLevel.MEDIUM and (command_count > 1 or len(matched_patterns) > 1):
            return True

        return False
