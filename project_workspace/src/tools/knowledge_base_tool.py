"""
MOD-013: KnowledgeBaseTool — RAG knowledge base retrieval tool (LangChain BaseTool wrapper).
@author sub_agent_software_developer
@module MOD-013
@implements IFC-013-01
@depends MOD-008 (RAGService)
@covers REQ-FUNC-019
"""

from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from loguru import logger

from src.models.fix_plan import KnowledgeBaseResult
from src.llm.rag_service import RAGService


class KnowledgeBaseTool(BaseTool):
    """
    RAG 知识库检索工具，封装为 LangChain BaseTool。
    委托给 MOD-008 RAGService 执行语义检索。

    IFC-013-01: search(query, alert_type, top_k) → KnowledgeBaseResult
    """

    name: str = "knowledge_base_search"
    description: str = (
        "Search the network knowledge base for relevant fault cases, "
        "remediation plans, and command templates. "
        "Provide a natural language query and the alert type for filtering."
    )

    # ── 模块依赖注入 ──
    _rag_service: Optional[RAGService] = None

    def __init__(self, rag_service: Optional[RAGService] = None, **kwargs: Any):
        super().__init__(**kwargs)
        if rag_service is not None:
            self._rag_service = rag_service

    def set_rag_service(self, rag_service: RAGService) -> None:
        """注入 MOD-008 RAGService 实例。"""
        self._rag_service = rag_service

    # ── IFC-013-01: search ────────────────────────────────

    def search(self, query: str, alert_type: str, top_k: int = 5) -> KnowledgeBaseResult:
        """
        检索知识库。
        委托给 MOD-008 RAGService.search()。
        """
        if self._rag_service is None:
            logger.warning("RAGService not injected — returning empty result")
            return KnowledgeBaseResult(matches=[], count=0)

        matches = self._rag_service.search(query, alert_type, top_k)
        return KnowledgeBaseResult(matches=matches, count=len(matches))

    # ── LangChain BaseTool 接口 ──────────────────────────

    def _run(
        self,
        query: str = "",
        alert_type: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> str:
        """LangChain Tool 同步入口。"""
        result = self.search(query, alert_type, top_k)
        return str(result.model_dump())

    async def _arun(
        self,
        query: str = "",
        alert_type: str = "",
        top_k: int = 5,
        **kwargs: Any,
    ) -> str:
        """LangChain Tool 异步入口。"""
        result = self.search(query, alert_type, top_k)
        return str(result.model_dump())
