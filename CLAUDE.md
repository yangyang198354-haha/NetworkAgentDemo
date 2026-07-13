# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NetworkAgentDemo is a LangGraph-based network automation agent (Demo v0.2.0) that automates the "alert → diagnose → fix → verify → close" workflow for network devices. It includes a FastAPI backend, a Vue 3 Web UI for management, and systemd-based scheduled inspection.

**Deployment target**: Alibaba Cloud ECS (47.109.197.217), Python 3.11+, port 8001.

**Workspace layout**: All project source files live under `project_workspace/`. The `.claude/` directory and this CLAUDE.md are at the repo root. All commands below run from `project_workspace/`.

## Commands

### Backend (Python)

```bash
cd project_workspace

# Start the FastAPI server
python src/main.py

# Run all unit tests (CI mode — excludes e2e and slow tests)
python -m pytest tests/ -v --tb=short \
  --ignore=tests/test_e2e_webui.py \
  --ignore=tests/test_e2e_full.py \
  --ignore=tests/test_inspection_systemd_e2e.py \
  -k "not slow"

# Run a single test file
python -m pytest tests/test_alert_normalizer.py -v

# Run a single test function
python -m pytest tests/test_alert_normalizer.py::test_normalize_port_down -v

# Run the inspection CLI (normally triggered by systemd timer)
python -m src.inspection_cli run
```

### Frontend (Vue 3 + Vite)

```bash
cd project_workspace/webui
npm run dev      # Dev server with HMR
npm run build    # Production build → webui/dist/
```

### Environment

```bash
cp project_workspace/.env.example project_workspace/.env
```

## Architecture

**Style**: Modular Layered Monolith — 5 logical layers within a single FastAPI process.

### Layer model

| Layer | Modules | Description |
|-------|---------|-------------|
| Trigger | WebhookReceiver, inspection_cli | Alert ingestion via HTTP webhook + systemd-triggered inspection |
| Orchestration | StateGraphEngine, AlertNormalizer, NodeHandlers | 14-node LangGraph StateGraph with Interrupt for human approval |
| LLM & Knowledge | LLMService, TemplateEngine, RAGService, OutputValidator | DeepSeek API for LLM, ChromaDB + OpenAI embeddings for RAG |
| Tools | SwitchConfigTool, SwitchDiagTool, BackupTool, KnowledgeBaseTool | Mock network device operations (strategy pattern, TP-Link ready) |
| Security & Infra | ConfigManager, AuditLogger, RiskAssessor | YAML config, audit trail, risk scoring |

### LangGraph workflow (14 nodes, 5 conditional edges)

```
receive_alert → parse_alert → validate_alert ──[invalid]──→ finish_report
                                   │
                            [valid] ▼
                  get_device_info → establish_ssh → collect_diag
                                                         │
                                              analyze_root_cause ──[failed]──→ finish_report
                                                         │
                                                  [success] ▼
                              generate_fix_plan → assess_risk ──[needs approval]──→ human_approval ──[rejected]──→ finish_report
                                                         │                                    │
                                                  [auto] ▼                             [approved] ▼
                                                backup_config ←──────────────────────────────────
                                                         │
                                                  [success] ▼
                              execute_fix → verify_fix ──→ finish_report
```

- The graph uses synchronous `StateGraph` with `MemorySaver` as checkpointer.
- `interrupt_before=["human_approval"]` pauses the graph for human decision.
- Workflows execute in background `threading.Thread` (LangGraph is sync, FastAPI is async).
- State is a `TypedDict` (`NetworkAgentState`, `src/models/state.py`).

### API surface

- **Legacy endpoints** (no auth): `/webhook/alert`, `/alerts/simulate`, `/approvals/pending`, `/approvals/{id}/decide`, `/workflow/{id}/state`, `/health`
- **Web UI API** (JWT-protected under `/api/*`): 8 routers — alerts, workflow, approvals, devices, inspection, knowledge, system config, dashboard
- JWT tokens issued via `/auth/login`; all `/api/*` routes require `Authorization: Bearer <token>`.
- SPA fallback: non-API routes serve `webui/dist/index.html`.

### Data layer

- **SQLite** (`data/webui.db`) via SQLAlchemy 2.0, WAL mode, foreign keys enabled.
- 11 ORM models, 7 repositories (pattern: each repo wraps `Session`).
- `Base.metadata.create_all()` on startup (no Alembic migrations in demo).
- `SessionLocal` is a module-level global set by `init_session()` at startup.

### systemd inspection (v0.2.0)

APScheduler was removed. Inspection now runs via:
- `src/systemd/systemctl_executor.py` — zero-dependency `systemctl` wrapper using `subprocess.run` with `shell=False`.
- `src/systemd/systemd_unit_manager.py` — manages timer/service unit files.
- `src/inspection_cli.py` — CLI entry point invoked by systemd timer. Exit codes: 0=SUCCESS, 1=PARTIAL, 2=FAILURE.

### Frontend

Vue 3 + TypeScript + Vite + Element Plus + ECharts + Pinia + Vue Router. Auto-import configured via `unplugin-vue-components` and `unplugin-auto-import`.

## Key conventions

- **Config**: `config/config.yaml` loaded by `ConfigManager`; env vars take precedence (pattern: `DEVICE_{NAME}_PASSWORD`).
- **LLM**: DeepSeek API for chat, OpenAI API for Chroma embeddings (falls back to in-memory keyword matching if OpenAI key is absent).
- **Mock tools**: All device tools (`SwitchConfigTool`, `SwitchDiagTool`, `BackupTool`) run in mock mode (`use_mock=True`). Real TP-Link integration is reserved.
- **Testing**: Known source defects (D-001, D-002) are patched at test time via `conftest.py`'s `sys.meta_path` hook — never modify `src/` to fix test imports.
- **pytest markers**: `slow` (deselect with `-k "not slow"`), `e2e` (requires remote VPS, excluded from CI unit job).
- **CI**: Unit tests on push/PR to master (Python 3.11 + 3.12); E2E tests only on `workflow_dispatch`.
