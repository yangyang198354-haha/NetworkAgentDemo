<file_header>
  <author_agent>devops_engineer</author_agent>
  <timestamp>2026-07-10T08:00:00Z</timestamp>
  <project_name>NetworkAgentDemo</project_name>
  <version>0.2.0</version>
  <input_files>
    <file>architecture/architecture_design.md</file>
    <file>architecture/tech_stack.md</file>
    <file>testing/unit_test_report.md</file>
    <file>testing/integration_test_report.md</file>
    <file>testing/e2e_test_report.md</file>
    <file>.github/workflows/test.yml</file>
    <file>requirements.txt</file>
    <file>webui/package.json</file>
  </input_files>
  <phase>PHASE_10</phase>
  <status>DRAFT</status>
</file_header>

# CI/CD 流水线定义 — NetworkAgentDemo v0.2.0

---

## 流水线概览

```
[Source Push] → [Backend Test] → [Frontend Build] → [Artifact Package] → [Deploy Staging] → [Deploy Prod]
                    │                    │
                    ▼                    ▼
               Python 3.11+3.12     Node.js 20 LTS
               pytest (unit+int)    npm run build
```

---

## 阶段定义表

| 阶段名 | 触发条件 | 命令 | 成功标准 | 失败处理 |
|--------|---------|------|---------|----------|
| **Checkout** | push/PR to main/master, workflow_dispatch | `actions/checkout@v4` | 代码完整检出 | abort-and-notify |
| **Setup Python** | 随 test job 自动 | `actions/setup-python@v5` with python-version matrix | Python 3.11 / 3.12 就绪, pip cache 命中 | abort-and-notify |
| **Install Deps** | 随 test job 自动 | `pip install --upgrade pip && pip install -r requirements.txt` | exit code 0, 所有依赖解析成功 | abort-and-notify |
| **Backend Unit Test** | 随 test job 自动 | `python -m pytest tests/ -v --tb=short -m "not integration"` | 通过率 >= 80%, exit code 0 | abort-and-notify; upload artifact for debugging |
| **Backend Integration Test** | 随 test job 自动 | `python -m pytest tests/ -v --tb=short -m "integration"` | 通过率 >= 90%, exit code 0 | abort-and-notify; upload artifact |
| **Frontend Install** | 需要前端变更时 | `cd webui && npm ci` | exit code 0, node_modules 创建 | abort-and-notify |
| **Frontend Build** | 需要前端变更时 | `cd webui && npm run build` | exit code 0, dist/ 目录生成 | abort-and-notify |
| **Package Artifact** | 仅 main/master 分支 push | tar czf release.tar.gz --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='node_modules' . | release.tar.gz 生成, 大小 < 50MB | retry(1) then abort |
| **Deploy Staging** | Artifact 就绪 + 手动批准 | scp release.tar.gz to VPS → extract → pip install → systemctl restart | health endpoint 返回 200 | abort, notify, 保留 artifact 供调试 |
| **Deploy Prod** | Staging 验证通过 + PM 手动触发 | 同 Staging 步骤, 目标为 prod service | 所有 health checks 通过 + GenPlatform 未受影响 | 自动回滚 (ROLLBACK-001) |

---

## GitHub Actions 完整配置 (.github/workflows/test.yml)

基于现有 CI 流水线，增强为支持 Web UI v0.2.0 的版本：

```yaml
name: Run Tests

on:
  push:
    branches: [master, main]
  pull_request:
    branches: [master, main]
  workflow_dispatch:

jobs:
  backend-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run unit tests
        run: |
          python -m pytest tests/ -v --tb=short \
            --ignore=tests/test_integration.py \
            --junitxml=test-results/unit-${{ matrix.python-version }}.xml
        continue-on-error: false

      - name: Run integration tests
        run: |
          python -m pytest tests/test_integration.py -v --tb=short \
            --junitxml=test-results/integration-${{ matrix.python-version }}.xml
        continue-on-error: false

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results-py${{ matrix.python-version }}
          path: test-results/
          retention-days: 30

  frontend-build:
    runs-on: ubuntu-latest
    needs: backend-test
    # 仅在有前端变更时运行（可根据实际需要调整）
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: webui/package-lock.json

      - name: Install frontend dependencies
        run: |
          cd webui
          npm ci

      - name: Build frontend
        run: |
          cd webui
          npm run build

      - name: Upload frontend dist
        uses: actions/upload-artifact@v4
        with:
          name: webui-dist
          path: webui/dist/
          retention-days: 7

  deploy-ready-check:
    runs-on: ubuntu-latest
    needs: [backend-test, frontend-build]
    if: github.ref == 'refs/heads/main' || github.ref == 'refs/heads/master'
    steps:
      - name: All checks passed
        run: |
          echo "✅ Backend tests (Python 3.11 + 3.12) PASSED"
          echo "✅ Frontend build PASSED"
          echo "✅ Ready for deployment"
```

---

## 本地 CI 替代方案（非 GitHub 仓库）

如果仓库不在 GitHub 上，使用本地脚本 `ci_local.sh`：

```bash
#!/bin/bash
# ci_local.sh — NetworkAgentDemo 本地 CI 脚本
set -e

echo "=== CI: Install Backend Dependencies ==="
python3.11 -m pip install --upgrade pip
pip install -r requirements.txt

echo "=== CI: Run Unit Tests ==="
python3.11 -m pytest tests/ -v --tb=short --ignore=tests/test_integration.py \
  --junitxml=test-results/unit.xml

echo "=== CI: Run Integration Tests ==="
python3.11 -m pytest tests/test_integration.py -v --tb=short \
  --junitxml=test-results/integration.xml

echo "=== CI: Build Frontend ==="
cd webui
npm ci
npm run build
cd ..

echo "=== CI: All checks PASSED ==="
```

---

## Artifact 管理规则

| 配置项 | 值 |
|--------|-----|
| **存储位置** | GitHub Actions Artifacts (CI) / VPS `/opt/NetworkAgentDemo.backup.{date}` (部署备份) |
| **命名格式** | `networkagent-demo-v{version}-{git_sha_short}.tar.gz` |
| **晋升条件** | main/master 分支 + 后端测试全绿 (Python 3.11 + 3.12) + 前端构建成功 |
| **保留策略** | CI artifacts: 30 天 / VPS 备份: 保留最近 3 个版本 |

---

## 环境配置矩阵

| 配置项 | Dev 环境 (本地) | Staging 环境 | Prod 环境 (VPS) |
|--------|----------------|-------------|------------------|
| **Python 版本** | 3.14.6 (开发机) | 3.11 | 3.11.13 |
| **Node.js** | 任意 | 20 LTS | 20.20.2 |
| **端口** | 8000 | 8001 | 8001 |
| **数据库** | SQLite (本地文件) | SQLite | SQLite |
| **ChromaDB** | fallback 模式 | fallback 模式 | fallback 模式 (sqlite3 < 3.35.0) |
| **LLM API** | Mock/DEEPSEEK_API_KEY | DEEPSEEK_API_KEY | DEEPSEEK_API_KEY |
| **副本数** | 1 | 1 | 1 |
| **资源限制** | 无 | 无 (Demo) | 共享 ECS (2 vCPU, 4 GB RAM) |
| **GenPlatform 共存** | N/A | N/A | 端口 80/8000, 不可破坏 |

---

## 安全与合规

- **禁止硬编码凭证**: 所有 API Key 通过 `.env` 环境变量注入，不提交到 Git
- **CI Secrets**: GitHub Actions 使用 `secrets.DEEPSEEK_API_KEY` 等 encrypted secrets
- **输出净化**: CI 日志中禁止输出 API Key（使用 `***` 掩码）
- **门控要求**: 测试通过率 < 阈值时自动阻断部署流程
