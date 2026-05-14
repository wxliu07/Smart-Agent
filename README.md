# AgentChat

AgentChat 是一个前后端分离的智能体对话平台。后端基于 FastAPI、LangChain、LangGraph、MCP 与 RAG 能力构建，前端基于 Vue 3、Vite、TypeScript 与 Element Plus 构建，支持多模型对话、工具调用、知识库检索、多智能体工作流、MCP 服务接入和使用量统计。

## 功能概览

- 多模型接入：支持对话模型、工具调用模型、推理模型、Embedding、Rerank、视觉模型与文生图模型的独立配置。
- 智能体与工具：内置天气、搜索、论文检索、网页抓取、文件转换、图片理解、邮件发送、快递查询等工具，并支持自定义工具扩展。
- RAG 知识库：支持多格式文档解析、分块、向量检索、Elasticsearch 关键词检索与召回增强问答。
- MCP 集成：支持标准 MCP 服务和项目内置 MCP Server，便于把外部工具接入智能体运行时。
- 用户与数据：包含用户认证、对话历史、Agent 配置、模型配置、工具配置、知识库和调用统计等模块。
- 前端工作台：提供对话、知识库、Agent 管理、模型管理、工具管理、MCP Server、工作区和数据看板等页面。

## 技术栈

后端：Python 3.12+、FastAPI、Uvicorn、LangChain、LangGraph、SQLModel、MySQL、Redis、Elasticsearch、Milvus/ChromaDB、MCP。

前端：Vue 3、Vite、TypeScript、Element Plus、Pinia、Vue Router、Axios、ECharts。

## 项目结构

```text
AgentChat/
├─ docker/                         # Docker、Compose、Nginx 和生产配置模板
├─ docs/                           # 与项目代码、接口、数据库、架构相关的文档
├─ scripts/                        # 本地启动和维护脚本
├─ src/
│  ├─ backend/
│  │  ├─ agentchat/
│  │  │  ├─ api/                   # FastAPI 路由与接口服务
│  │  │  ├─ config/                # 工具和 MCP 默认配置
│  │  │  ├─ core/                  # 模型、Agent、回调等核心能力
│  │  │  ├─ database/              # SQLModel 模型、DAO、初始化逻辑
│  │  │  ├─ mcp_servers/           # 内置 MCP Server
│  │  │  ├─ prompts/               # Prompt 模板
│  │  │  ├─ schema/                # 请求/响应数据结构
│  │  │  ├─ services/              # RAG、MCP、记忆、搜索、工作区等服务
│  │  │  ├─ tools/                 # 内置工具实现
│  │  │  ├─ main.py                # FastAPI 应用入口
│  │  │  └─ settings.py            # YAML 配置加载
│  │  └─ fastapi_jwt_auth/         # 项目内兼容版本 JWT 认证模块
│  └─ frontend/
│     ├─ src/
│     │  ├─ apis/                  # 前端 API 封装
│     │  ├─ components/            # 通用组件
│     │  ├─ pages/                 # 业务页面
│     │  ├─ router/                # 路由
│     │  ├─ store/                 # Pinia 状态
│     │  └─ utils/                 # 工具函数
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

## 敏感配置

不要把真实 API Key、数据库密码、JWT 密钥、OSS AccessKey、Webhook Token 或任何个人配置提交到 GitHub。

本项目默认从 `src/backend/agentchat/config.yaml` 读取本地配置。该文件已被 `.gitignore` 忽略，应该只保留在本机或服务器上。首次运行时可以复制模板：

```powershell
Copy-Item src/backend/agentchat/config.example.yaml src/backend/agentchat/config.yaml
```

然后只在 `config.yaml` 中填写真实值。Docker 部署时使用：

```powershell
Copy-Item docker/config.production.example.yaml docker/config.yaml
Copy-Item docker/docker.env.example docker/docker.env
```

同样只在 `docker/config.yaml` 和 `docker/docker.env` 中填写真实密钥。

如果真实密钥曾经被提交过，即使后来加入 `.gitignore` 也不算安全。建议立即做三件事：

1. 到对应平台轮换或删除已经泄露的 API Key。
2. 确认包含密钥的文件已从 Git 索引移除，例如 `git rm --cached src/backend/agentchat/config.yaml`。
3. 如果提交历史已经包含密钥，使用 `git filter-repo` 或 BFG 清理历史后再推送。

## 本地启动

### 1. 准备服务

本地开发通常需要 MySQL、Redis，以及按配置决定是否启用 Elasticsearch、Milvus 或 ChromaDB。请确保 `src/backend/agentchat/config.yaml` 中的连接地址与实际服务一致。

### 2. 安装后端依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt
```

### 3. 启动后端

```powershell
cd src/backend
uvicorn agentchat.main:app --host 0.0.0.0 --port 7860 --reload
```

健康检查：

```text
http://localhost:7860/health
```

### 4. 安装并启动前端

```powershell
cd src/frontend
npm install
npm run dev
```

默认前端地址通常为：

```text
http://localhost:5173
```

### 5. 一键开发启动

```powershell
python scripts/start.py
```

## Docker 部署

```powershell
Copy-Item docker/config.production.example.yaml docker/config.yaml
Copy-Item docker/docker.env.example docker/docker.env
cd docker
docker compose up -d
```

常用文件：

- `docker/docker-compose.yml`：基础 Compose 配置。
- `docker/docker-compose.prod.yml`：生产部署配置。
- `docker/nginx.conf`：前端静态资源与后端代理配置。
- `docker/config.production.example.yaml`：生产配置模板，不要直接写真实 key 后提交。
- `docker/docker.env.example`：环境变量模板，不要直接写真实密码后提交。

## 常用命令

```powershell
# 后端依赖
pip install -r requirements.txt

# 后端启动
cd src/backend
uvicorn agentchat.main:app --port 7860 --reload

# 前端开发
cd src/frontend
npm run dev

# 前端构建
npm run build

# 前端类型检查
npm run lint
```

## 文档

建议保留与代码直接相关的文档：

- `docs/api.md`：接口说明。
- `docs/database.md`：数据库结构。
- `docs/core.md`：核心模块说明。
- `docs/service.md`：服务层说明。
- `docs/backend-architecture.md`：后端架构说明。
- `docs/backend-files-analysis.md`：后端文件结构说明。
- `docs/migration.md`：迁移记录。
- `docs/agentchat.sql`：数据库初始化 SQL。

其他本地资料已通过 `.gitignore` 隐藏，避免推送到 GitHub。

## 提交前检查

```powershell
git status --short
git diff --cached --name-only
git grep -n -I "api_key\|secret_key\|access_key\|password\|token" -- . ":!docs/*" ":!*.example*" ":!*.md"
```

如果发现真实密钥，先移除或改成环境变量/本地配置，再提交。

## License

本项目使用 MIT License，详见 `LICENSE`。
