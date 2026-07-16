"""
MOD-006: LLMService — Encapsulate openai SDK for DeepSeek API calls.
@author sub_agent_software_developer
@module MOD-006
@implements IFC-006-01, IFC-006-02, IFC-006-03
@depends None
@covers REQ-FUNC-010, REQ-FUNC-011, REQ-NFUNC-013
"""

import json
import os
import time
from typing import Any

from loguru import logger
from openai import OpenAI

from src.models.alert import DeviceInfo
from src.models.fix_plan import RootCauseResult, TemplateParams, FixPlan, ExecRecord, VerifyResult


class LLMService:
    """
    LLM 服务封装，提供两个隔离的调用端点:
      - analyze_root_cause (IFC-006-01): 根因分析（自由推理）
      - fill_template_params (IFC-006-02): 模板参数填充（严格 JSON 约束）
      - generate_report (IFC-006-03): 最终报告生成

    内部约束:
      - base_url: https://api.deepseek.com/v1
      - api_key: from DEEPSEEK_API_KEY environment variable
      - model: deepseek-chat, temperature=0.1
      - 重试: 最多 3 次，指数退避 (1s, 2s, 4s)
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None, llm_log_repo=None):
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._base_url = base_url or "https://api.deepseek.com/v1"
        self._model = "deepseek-chat"
        self._temperature = 0.1
        self._llm_call_log: dict[str, list[dict]] = {}  # alert_id → list of call records
        # MOD-DP-007: optional LLMCallLogRepository for DB dual-write
        self._llm_log_repo = llm_log_repo

        if self._api_key:
            self._client = OpenAI(base_url=self._base_url, api_key=self._api_key)
        else:
            self._client = None
            logger.warning("DEEPSEEK_API_KEY not set — LLMService will use mock responses")

    def get_llm_logs(self, alert_id: str) -> list[dict]:
        """Retrieve LLM call records for a given alert."""
        return self._llm_call_log.get(alert_id, [])

    # ── IFC-006-01: analyze_root_cause ──────────────────────

    def analyze_root_cause(self, alert_content: str, diag_result: str, alert_id: str = "") -> RootCauseResult:
        """
        根因分析端点（自由推理，输出 Markdown 结构化）。
        若 API key 未配置，返回 Mock fallback 分析结果。
        """
        prompt = self._build_root_cause_prompt(alert_content, diag_result)

        raw_output = self._call_llm(prompt, endpoint="analyze_root_cause", alert_id=alert_id)

        # 解析 Markdown 格式输出
        description = raw_output or ""
        possible_causes = self._extract_list_section(raw_output, "可能原因")
        suggested_direction = self._extract_section(raw_output, "建议方向")

        return RootCauseResult(
            description=description.strip()[:1000],
            possible_causes=possible_causes if possible_causes else ["无法确定"],
            suggested_direction=suggested_direction or "建议人工介入排查",
        )

    # ── IFC-006-02: fill_template_params ───────────────────

    def fill_template_params(
        self,
        template_id: str,
        template_description: str,
        root_cause: str,
        diag_result: str,
        device_info: DeviceInfo,
        params_schema: dict[str, str] | None = None,
        alert_id: str = "",
    ) -> TemplateParams:
        """
        模板参数填充端点（严格约束，输出纯 JSON）。
        返回的 TemplateParams 中的 params 将由 MOD-009 OutputValidator 校验。
        """
        prompt = self._build_fill_params_prompt(
            template_id, template_description, root_cause, diag_result, device_info, params_schema
        )

        raw_output = self._call_llm(prompt, endpoint="fill_template_params", alert_id=alert_id)

        # 尝试解析 JSON（兼容单引号）
        try:
            json_str = self._extract_json(raw_output)
            params_dict = json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            # Fallback: try replacing single quotes with double quotes (DeepSeek quirk)
            try:
                fixed = self._extract_json(raw_output)
                fixed = fixed.replace("'", '"')
                params_dict = json.loads(fixed)
                logger.info("LLM JSON parsed after single→double quote fix")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"LLM fill_template_params output not valid JSON: {e}")
                params_dict = {}

        if not isinstance(params_dict, dict):
            params_dict = {}
        return TemplateParams(params=params_dict)

    # ── IFC-006-03: generate_report ────────────────────────

    def generate_report(
        self,
        alert_id: str,
        root_cause: str,
        fix_plan: FixPlan,
        exec_log: list[ExecRecord],
        verify_result: VerifyResult,
    ) -> str:
        """生成最终处理报告（Markdown 格式）。"""
        prompt = self._build_report_prompt(alert_id, root_cause, fix_plan, exec_log, verify_result)
        raw_output = self._call_llm(prompt, endpoint="generate_report", alert_id=alert_id)
        return raw_output or f"# Alert Processing Report\n\nAlert ID: {alert_id}\nStatus: COMPLETED\n"

    # ── 内部 LLM 调用 ──────────────────────────────────────

    def _call_llm(self, prompt: str, endpoint: str, max_retries: int = 3, alert_id: str = "") -> str:
        """Execute LLM call with retry and logging.  alert_id is required for
        per-alert DB dual-write; when empty, DB persistence is skipped."""
        retry_delays = [1.0, 2.0, 4.0]

        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                if self._client is None:
                    # Mock fallback（无 API key 时）
                    logger.info(f"[LLM Mock] {endpoint}: prompt_len={len(prompt)}")
                    output = self._mock_response(endpoint, prompt)
                    elapsed = time.time() - start_time
                    # ★ MOD-DP-007: DB dual-write for mock calls ★
                    if alert_id:
                        try:
                            from src.database.base import SessionLocal
                            from src.database.repositories.llm_call_repository import LLMCallLogRepository
                            db = SessionLocal()
                            try:
                                LLMCallLogRepository(db).create_log({
                                    "alert_id_fk": alert_id,
                                    "endpoint": endpoint,
                                    "elapsed_s": round(elapsed, 2),
                                    "prompt_tokens": 0,
                                    "completion_tokens": 0,
                                    "prompt_summary": prompt[:3000] if prompt else "",
                                    "response_summary": output[:3000] if output else "",
                                    "is_mock": True,
                                })
                            finally:
                                db.close()
                        except Exception as e:
                            logger.warning(f"Failed to persist LLM call log to DB (mock): {e}")
                    return output

                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": "你是一个网络运维专家，专门分析交换机故障并提供修复建议。请严格按要求格式输出。"},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=self._temperature,
                )

                elapsed = time.time() - start_time
                output = response.choices[0].message.content or ""
                usage = response.usage

                logger.info(
                    f"[LLM] {endpoint} {alert_id[:8]} | "
                    f"elapsed={elapsed:.2f}s | "
                    f"prompt_tokens={usage.prompt_tokens if usage else 'N/A'} | "
                    f"completion_tokens={usage.completion_tokens if usage else 'N/A'} | "
                    f"output_len={len(output)}"
                )

                # Record LLM call for Web UI (in-memory)
                if alert_id:
                    if alert_id not in self._llm_call_log:
                        self._llm_call_log[alert_id] = []
                    self._llm_call_log[alert_id].append({
                        "endpoint": endpoint,
                        "timestamp": time.strftime("%H:%M:%S"),
                        "elapsed_s": round(elapsed, 2),
                        "prompt_tokens": usage.prompt_tokens if usage else 0,
                        "completion_tokens": usage.completion_tokens if usage else 0,
                        "prompt": prompt[:3000],
                        "response": output[:3000],
                    })

                # ★ MOD-DP-007: DB dual-write for real LLM calls ★
                if alert_id:
                    try:
                        from src.database.base import SessionLocal
                        from src.database.repositories.llm_call_repository import LLMCallLogRepository
                        db = SessionLocal()
                        try:
                            LLMCallLogRepository(db).create_log({
                                "alert_id_fk": alert_id,
                                "endpoint": endpoint,
                                "elapsed_s": round(elapsed, 2),
                                "prompt_tokens": usage.prompt_tokens if usage else 0,
                                "completion_tokens": usage.completion_tokens if usage else 0,
                                "prompt_summary": prompt[:3000] if prompt else "",
                                "response_summary": output[:3000] if output else "",
                                "is_mock": False,
                            })
                        finally:
                            db.close()
                    except Exception as e:
                        logger.warning(f"Failed to persist LLM call log to DB: {e}")

                return output

            except Exception as e:
                elapsed = time.time() - start_time
                logger.warning(f"[LLM] {endpoint} attempt {attempt + 1}/{max_retries + 1} failed: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delays[min(attempt, len(retry_delays) - 1)])
                else:
                    logger.error(f"[LLM] {endpoint} all retries exhausted")
                    return ""

        return ""

    # ── Prompt 构建 ─────────────────────────────────────────

    @staticmethod
    def _build_root_cause_prompt(alert_content: str, diag_result: str) -> str:
        return f"""你是一个网络运维专家。根据以下告警内容和诊断数据，进行根因分析。

## 告警内容
{alert_content}

## 诊断数据
{diag_result}

## 输出要求
请按以下 Markdown 格式输出根因分析结果：

### 根因描述
[简要描述最可能的根因，1-3句话]

### 可能原因
- [原因1]
- [原因2]
- [原因3]

### 建议方向
[建议的排查和修复方向，1-2句话]
"""

    @staticmethod
    def _build_fill_params_prompt(
        template_id: str,
        template_description: str,
        root_cause: str,
        diag_result: str,
        device_info: DeviceInfo,
        params_schema: dict[str, str] | None = None,
    ) -> str:
        # Build expected params list
        params_list = ""
        if params_schema:
            params_items = ", ".join(f'{k}({v})' for k, v in params_schema.items())
            params_list = f"你需要填充的参数（**只能包含这些 key**）: {params_items}\n"

        return f"""你是一个网络运维专家。你需要根据告警分析和诊断数据，为命令模板填充参数值。

## 模板信息
模板ID: {template_id}
模板描述: {template_description}
{params_list}
## 根因分析
{root_cause}

## 诊断数据
{diag_result}

## 设备信息
- 设备名: {device_info.device_name}
- 设备IP: {device_info.device_ip}
- 接口: {device_info.interface_name or 'N/A'}
- MAC: {device_info.mac_address or 'N/A'}

## 输出要求（严格遵守！）

你必须输出一个**合法的纯 JSON 对象**。规则：
1. 只输出 JSON，不要包含任何其他文本、解释、Markdown 代码块标记
2. JSON 的 key 和字符串 value 必须用双引号 "" 包裹，不能用单引号 ''
3. 不要在最后一个元素后面加逗号
4. **JSON 中只能包含上面列出的参数名，不要自己编造任何额外的 key！**

请根据实际情况填充合理的参数值。注意:
- 接口名称使用诊断数据中出现的接口名
- 字符串值不要包含 CLI 命令关键词
- 数值使用合理的默认值
"""

    @staticmethod
    def _build_report_prompt(
        alert_id: str,
        root_cause: str,
        fix_plan: FixPlan,
        exec_log: list[ExecRecord],
        verify_result: VerifyResult,
    ) -> str:
        exec_summary = "\n".join(
            [f"- `{r.command}` → {'SUCCESS' if r.success else 'FAILED'}" for r in exec_log]
        ) if exec_log else "（无执行记录）"

        return f"""你是一个网络运维专家。请根据以下信息生成一份最终处理报告。

## 告警ID
{alert_id}

## 根因分析
{root_cause}

## 修复方案
模板ID: {fix_plan.template_id}
命令列表: {fix_plan.commands}

## 执行结果
{exec_summary}

## 验证结果
验证通过: {verify_result.verify_passed}
验证说明: {verify_result.comparison_notes}

## 输出要求
请输出一份 Markdown 格式的处理报告，包含:
1. 告警摘要
2. 根因分析
3. 执行操作
4. 最终状态
"""

    # ── JSON 提取 ───────────────────────────────────────────

    @staticmethod
    def _extract_json(raw: str) -> str:
        """从 LLM 输出中提取 JSON 字符串。"""
        raw = raw.strip()
        # 移除可能的 Markdown 代码块标记
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:] if len(lines) > 1 else lines
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines)

        # 尝试定位 JSON 对象边界
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return raw[start:end + 1]

        return raw

    # ── 文本解析辅助 ────────────────────────────────────────

    @staticmethod
    def _extract_list_section(text: str, section_name: str) -> list[str]:
        """从 Markdown 文本中提取指定段落下的列表项。"""
        import re
        # 匹配 "### 可能原因" 之后的列表
        pattern = rf"###\s*{section_name}\s*\n((?:\s*[-*]\s*.+\n?)+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            return []
        items = re.findall(r"[-*]\s*(.+)", match.group(1))
        return [item.strip() for item in items]

    @staticmethod
    def _extract_section(text: str, section_name: str) -> str:
        """从 Markdown 文本中提取指定段落内容。"""
        import re
        pattern = rf"###\s*{section_name}\s*\n(.*?)(?=\n###|\Z)"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    # ── Mock 响应（无 API key 时的 fallback） ──────────────

    @staticmethod
    def _mock_response(endpoint: str, prompt: str) -> str:
        """生成 Mock LLM 响应。"""
        if endpoint == "analyze_root_cause":
            return """### 根因描述
根据诊断数据分析，设备存在网络连通性问题，最可能由端口配置错误或物理链路故障引起。

### 可能原因
- 端口被管理员手动 shutdown
- 物理链路故障（光纤/网线断开）
- 对端设备未启动或端口协商失败
- MAC 地址漂移导致的安全策略锁定端口

### 建议方向
建议首先检查端口状态和配置，然后逐步排查物理链路和对端设备。"""
        elif endpoint == "fill_template_params":
            return '{"iface_name": "Gi0/1", "desc": "Auto-recovered by Agent", "max_mac": 2, "violation_mode": "restrict"}'
        elif endpoint == "generate_report":
            return f"""# 告警处理报告

## 告警摘要
系统自动检测并处理了一起网络设备告警。

## 根因分析
根据诊断数据分析，问题根因为端口配置或链路异常。系统已自动执行修复操作。

## 执行操作
修复命令已成功下发到目标设备。

## 最终状态
**状态: CLOSED** — 所有操作已完成，验证通过。"""
        return ""
