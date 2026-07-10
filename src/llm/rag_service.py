"""
MOD-008: RAGService — Chroma vector database management for knowledge retrieval.
@author sub_agent_software_developer
@module MOD-008
@implements IFC-008-01, IFC-008-02, IFC-008-03
@depends None
@covers REQ-FUNC-019, REQ-FUNC-021, REQ-FUNC-022
"""

import json
import os
from pathlib import Path
from typing import Optional

from loguru import logger

from src.models.fix_plan import KnowledgeRef, KnowledgeDocument


class RAGService:
    """
    Chroma 向量数据库管理服务。
    封装文档嵌入、索引持久化、语义检索和元数据过滤。

    Chroma 配置:
      - 持久化路径: ./data/chroma_db/
      - 集合名称: network_knowledge
      - 嵌入模型: text-embedding-3-small (via openai SDK)
      - 降级: 无 API key 时使用简单关键词匹配 fallback

    实现 IFC-008-01 (search), IFC-008-02 (index_documents), IFC-008-03 (get_template_by_id).
    """

    def __init__(
        self,
        persist_path: str = "./data/chroma_db/",
        collection_name: str = "network_knowledge",
        similarity_threshold: float = 0.6,
    ):
        self._persist_path = persist_path
        self._collection_name = collection_name
        self._similarity_threshold = similarity_threshold
        self._chroma_client = None
        self._collection = None
        self._embedding_model = "text-embedding-3-small"
        self._use_chroma = False

        # 内存后备存储（当 Chroma 不可用时）
        self._fallback_docs: list[KnowledgeDocument] = []

    def initialize(self) -> None:
        """初始化 Chroma 连接（尝试真实 Chroma，失败则使用内存 fallback）。"""
        try:
            import chromadb
            from chromadb.config import Settings

            persist_dir = Path(self._persist_path)
            persist_dir.mkdir(parents=True, exist_ok=True)

            self._chroma_client = chromadb.PersistentClient(
                path=str(persist_dir.absolute()),
                settings=Settings(anonymized_telemetry=False),
            )

            # 尝试获取或创建集合
            try:
                self._collection = self._chroma_client.get_collection(self._collection_name)
                logger.info(f"Chroma collection '{self._collection_name}' loaded ({self._collection.count()} docs)")
            except Exception:
                self._collection = self._chroma_client.create_collection(
                    name=self._collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info(f"Chroma collection '{self._collection_name}' created")

            self._use_chroma = True
            logger.info(f"RAGService initialized with Chroma at {self._persist_path}")

        except ImportError:
            logger.warning("chromadb not installed — RAGService using in-memory fallback")
            self._use_chroma = False
        except Exception as e:
            logger.warning(f"Chroma initialization failed: {e} — RAGService using in-memory fallback")
            self._use_chroma = False

    # ── IFC-008-01: search ─────────────────────────────────

    def search(self, query: str, alert_type: str, top_k: int = 5) -> list[KnowledgeRef]:
        """
        语义搜索 + 元数据过滤（where={"alert_type": alert_type}）。
        相似度阈值过滤（默认 ≥ 0.6，由 ConfigManager 配置）。
        """
        if self._use_chroma and self._collection:
            return self._chroma_search(query, alert_type, top_k)
        else:
            return self._fallback_search(query, alert_type, top_k)

    # ── IFC-008-02: index_documents ────────────────────────

    def index_documents(self, documents: list[KnowledgeDocument]) -> int:
        """
        将知识文档向量化并写入 Chroma 索引。
        返回成功索引的文档数。
        """
        if not documents:
            return 0

        count = 0
        for doc in documents:
            if self._use_chroma and self._collection:
                self._index_one_embedding(doc)
            self._fallback_docs.append(doc)
            count += 1

        logger.info(f"RAGService indexed {count} documents")
        return count

    # ── IFC-008-03: get_template_by_id ────────────────────

    def get_template_by_id(self, template_id: str) -> Optional[KnowledgeDocument]:
        """通过模板 ID 精确查找命令模板文档。"""
        for doc in self._fallback_docs:
            if doc.template_id == template_id:
                return doc
        return None

    # ── 种子数据加载 ───────────────────────────────────────

    def load_seed_knowledge(self, seed_file: str = "./resources/knowledge/seed_knowledge.json") -> int:
        """从种子数据文件加载知识文档。"""
        seed_path = Path(seed_file)
        if not seed_path.exists():
            logger.warning(f"Seed knowledge file not found: {seed_file}")
            return self._load_builtin_seeds()

        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load seed knowledge: {e}")
            return self._load_builtin_seeds()

        documents = [KnowledgeDocument(**item) for item in data if isinstance(item, dict)]
        if documents:
            return self.index_documents(documents)
        return self._load_builtin_seeds()

    def _load_builtin_seeds(self) -> int:
        """加载内嵌的 10 条示例知识条目。"""
        builtin = [
            KnowledgeDocument(
                doc_id="SEED-001", title="MAC 地址漂移 — 端口安全加固",
                content="MAC 地址在同一 VLAN 中出现在多个端口时，表明可能存在二层环路或 MAC 欺骗攻击。修复方案为在接入端口启用 port-security 限制学习 MAC 数量。",
                alert_type="MAC_FLAPPING", doc_type="case",
                template_id="TPL-MAC-PORT-SECURITY",
            ),
            KnowledgeDocument(
                doc_id="SEED-002", title="MAC 地址漂移 — STP 检查",
                content="检查生成树协议状态，确认是否存在 STP 拓扑变更导致的 MAC 表刷新。若启用 portfast 但未启用 bpduguard 可能导致环路。",
                alert_type="MAC_FLAPPING", doc_type="plan",
                template_id="TPL-MAC-CLEAR",
            ),
            KnowledgeDocument(
                doc_id="SEED-003", title="MAC 地址漂移 — 运维手册",
                content="排查步骤: 1) show mac address-table 定位漂移端口; 2) show logging 查看 syslog; 3) 在接入端口启用 port-security; 4) 检查 VLAN 配置避免环路。",
                alert_type="MAC_FLAPPING", doc_type="plan",
            ),
            KnowledgeDocument(
                doc_id="SEED-004", title="端口 Down — 自动恢复",
                content="接口因链路故障或配置错误进入 down 状态。常见原因包括: 对端设备未启动、光纤链路中断、端口被 shutdown。修复时需先在接口下执行 no shutdown 并设置描述。",
                alert_type="PORT_DOWN", doc_type="case",
                template_id="TPL-PORT-ENABLE",
            ),
            KnowledgeDocument(
                doc_id="SEED-005", title="端口 Down — 管理员关闭场景",
                content="若端口为管理员手动 shutdown，需确认关闭原因后再恢复。如果是对端设备维护期间的临时关闭，需要在维护结束后取消 shutdown。",
                alert_type="PORT_DOWN", doc_type="plan",
                template_id="TPL-PORT-ENABLE",
            ),
            KnowledgeDocument(
                doc_id="SEED-006", title="端口 Down — 物理层排查",
                content="排查步骤: 1) show interface status 检查端口状态; 2) show interface 查看详细错误计数; 3) 检查光纤收发器光功率; 4) 更换光模块/光纤测试。",
                alert_type="PORT_DOWN", doc_type="plan",
                template_id="TPL-PORT-DISABLE",
            ),
            KnowledgeDocument(
                doc_id="SEED-007", title="CPU 利用率过高 — 进程分析",
                content="CPU 突发性升高常由 SNMP 轮询风暴、路由协议震荡或环路导致的数据平面流量引起。检查 show processes cpu 中 top 进程。",
                alert_type="CPU_HIGH", doc_type="case",
                template_id="TPL-CPU-RATE-LIMIT",
            ),
            KnowledgeDocument(
                doc_id="SEED-008", title="CPU 利用率过高 — CoPP 策略",
                content="通过控制平面策略（Control Plane Policing）限制发往 CPU 的管理流量速率。对 SNMP、SSH、ICMP 等管理协议设置合理的速率上限。",
                alert_type="CPU_HIGH", doc_type="plan",
                template_id="TPL-CPU-RATE-LIMIT",
            ),
            KnowledgeDocument(
                doc_id="SEED-009", title="CPU 利用率过高 — 应急处理",
                content="排查步骤: 1) show processes cpu 定位高CPU进程; 2) 检查是否遭受 DDoS; 3) 限制 SNMP 轮询频率; 4) 必要时重启相关进程。",
                alert_type="CPU_HIGH", doc_type="plan",
                template_id="TPL-CPU-PROCESS-RESTART",
            ),
            KnowledgeDocument(
                doc_id="SEED-010", title="通用配置备份规范",
                content="任何配置变更前必须通过 show running-config 备份当前配置。变更后确认设备运行正常再执行 write memory 保存。备份文件命名: {hostname}_{date}_pre_change.cfg",
                alert_type="CPU_HIGH", doc_type="template",
                template_id="TPL-BACKUP",
            ),
        ]
        return self.index_documents(builtin)

    # ── Chroma 搜索实现 ────────────────────────────────────

    def _chroma_search(self, query: str, alert_type: str, top_k: int) -> list[KnowledgeRef]:
        """通过 Chroma 执行语义搜索。"""
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=top_k,
                where={"alert_type": alert_type},
            )

            refs: list[KnowledgeRef] = []
            if not results or not results.get("ids") or not results["ids"][0]:
                return refs

            for i, doc_id in enumerate(results["ids"][0]):
                distance = results.get("distances", [[1.0]])[0][i] if results.get("distances") else 0.0
                relevance = 1.0 - distance if distance else 0.5
                metadata = results.get("metadatas", [[{}]])[0][i] if results.get("metadatas") else {}
                document = results.get("documents", [[""]])[0][i] if results.get("documents") else ""

                if relevance >= self._similarity_threshold:
                    refs.append(KnowledgeRef(
                        doc_id=doc_id,
                        title=metadata.get("title", doc_id),
                        content=document or "",
                        relevance_score=round(relevance, 4),
                        template_id=metadata.get("template_id"),
                    ))

            refs.sort(key=lambda r: r.relevance_score, reverse=True)
            return refs

        except Exception as e:
            logger.warning(f"Chroma search failed: {e} — falling back to in-memory search")
            return self._fallback_search(query, alert_type, top_k)

    def _index_one_embedding(self, doc: KnowledgeDocument) -> None:
        """通过 Chroma 索引单个文档（尝试 embedding，失败则跳过向量化仅存元数据）。"""
        try:
            # 尝试使用 openai embedding
            openai_key = os.environ.get("OPENAI_API_KEY", "")
            if openai_key:
                from openai import OpenAI
                client = OpenAI(api_key=openai_key)
                response = client.embeddings.create(
                    model=self._embedding_model,
                    input=doc.content[:8000],  # 截断长文本
                )
                embedding = response.data[0].embedding
                self._collection.add(
                    ids=[doc.doc_id],
                    embeddings=[embedding],
                    documents=[doc.content],
                    metadatas=[{
                        "title": doc.title,
                        "alert_type": doc.alert_type,
                        "doc_type": doc.doc_type,
                        "template_id": doc.template_id or "",
                    }],
                )
            else:
                # 无 embedding API key，仅存文档
                self._collection.add(
                    ids=[doc.doc_id],
                    documents=[doc.content],
                    metadatas=[{
                        "title": doc.title,
                        "alert_type": doc.alert_type,
                        "doc_type": doc.doc_type,
                        "template_id": doc.template_id or "",
                    }],
                )
        except Exception as e:
            logger.warning(f"Chroma indexing failed for doc {doc.doc_id}: {e}")

    # ── 内存 fallback 搜索 ─────────────────────────────────

    def _fallback_search(self, query: str, alert_type: str, top_k: int) -> list[KnowledgeRef]:
        """
        简单关键词匹配 fallback 搜索。
        当 Chroma 不可用时使用，按 alert_type 过滤 + 关键词匹配。
        """
        query_lower = query.lower()
        keywords = set(query_lower.split())

        scored: list[tuple[float, KnowledgeDocument]] = []
        for doc in self._fallback_docs:
            if doc.alert_type.upper() != alert_type.upper():
                continue

            content_lower = doc.content.lower()
            # 简单关键词匹配评分
            score = sum(1.0 for kw in keywords if kw in content_lower) / max(len(keywords), 1)
            scored.append((score, doc))

        # 按分数排序，取 top_k
        scored.sort(key=lambda x: x[0], reverse=True)
        results: list[KnowledgeRef] = []
        for score, doc in scored[:top_k]:
            if score >= self._similarity_threshold:
                results.append(KnowledgeRef(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    content=doc.content,
                    relevance_score=round(score, 4),
                    template_id=doc.template_id,
                ))

        return results
