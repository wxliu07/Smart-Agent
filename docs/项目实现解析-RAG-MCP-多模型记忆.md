# 项目实现解析: RAG、MCP、多模型与记忆机制

## 1. 文档目标

这份文档专门分析你截图里的三类能力:

1. 基于 `Milvus` 向量数据库和 `RAG` 的知识库管理
2. 基于 `MCP` 协议的动态服务加载、调度与扩展
3. 多模型切换、上下文记忆、思维过程可视化与模型参数管理

分析方式会尽量贴近真实面试场景:

- 先讲原理
- 再讲这个项目里是怎么落地的
- 最后讲你可以怎么对面试官解释

全文会尽量引用具体类、方法、数据流和字段设计，但不会贴整段完整代码，避免篇幅失控。

---

## 2. 整体结论先说清楚

从源码看，这个项目并不是简单“接了几个 AI 接口”的 Demo，而是已经形成了比较完整的 AI 应用平台骨架:

- 知识库部分，走的是典型 `解析 -> 分块 -> 向量化 -> Milvus 检索 -> Rerank -> 拼接上下文` 的 RAG 链路，并且对 `PDF -> Markdown -> Chunk` 做了较细的工程处理。
- MCP 部分，不只是“支持 MCP”这么一句，而是已经支持多种传输层配置，能动态读取远程 MCP Server 的工具描述，再包装成 LangChain/LangGraph 可调用工具。
- 多模型部分，不是单一聊天模型，而是把 `对话模型`、`工具调用模型`、`推理模型`、`Embedding 模型`、`Rerank 模型` 拆开管理。
- 记忆部分和知识库部分是两套体系:
  - 知识库偏“外部文档知识”
  - 记忆偏“对话过程中沉淀出的用户事实与上下文”

这几个点在面试里一定要讲清楚，因为它们体现的是“系统分层能力”，不是单点功能。

---

## 3. Milvus + RAG 知识库模块是怎么做的

### 3.1 先讲原理: RAG 本质是什么

RAG 的本质不是“把文档喂给大模型”，而是:

1. 把文档解析成适合检索的片段
2. 把片段转成向量
3. 用户提问时把问题也转成向量
4. 在向量库中找最相近的片段
5. 必要时再做关键词检索、重排、过滤
6. 把检索结果作为上下文拼进 Prompt
7. 让大模型基于“外部知识 + 原问题”作答

它解决的是大模型原生参数知识的三个问题:

- 知识过时
- 领域知识不全
- 无法直接引用企业私有文档

所以面试里一句话可以这么说:

> RAG 不是训练模型，而是把“知识访问”从参数记忆变成运行时检索。

---

### 3.2 这个项目的 RAG 主链路

知识库文件上传后的主流程，核心在 [knowledge_file.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/knowledge_file.py)。

关键方法:

- `KnowledgeFileService.create_knowledge_file`

它的流程非常清晰:

1. 创建知识文件记录
2. 更新解析状态为 `process`
3. 调用 `doc_parser.parse_doc_into_chunks(...)`
4. 调用 `RagHandler.index_milvus_documents(...)`
5. 如果开启 ES，再调用 `RagHandler.index_es_documents(...)`
6. 成功后把状态改成 `success`
7. 异常时改成 `fail`

这说明知识库的工程实现不是同步阻塞在接口层随便做一下，而是已经有“文件记录 + 解析状态 + 向量入库 + 错误状态”的完整生命周期。

你可以把这段逻辑概括成:

> 上传文件只是入口，真正关键的是后台把文件转换成可检索知识单元，并记录解析状态，保证知识库是可管理的。

---

### 3.3 文档解析层: 为什么不是直接按固定长度切

核心入口在 [parser.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/parser.py)。

关键方法:

- `DocParser.parse_doc_into_chunks`

它会按文件后缀分发到不同解析器:

- `md` -> `markdown_parser`
- `txt` -> `text_parser`
- `docx` -> `docx_parser`
- `pdf` -> `pdf_parser`
- `pptx` -> `pptx_parser`
- 图片 -> OCR/转文本后再切块
- Excel -> 转文本后再切块
- 其他类文本文件 -> 转 txt 后处理

这里体现出两个设计点:

1. 先做“格式归一化”，再做 chunk
2. chunk 逻辑尽量复用，而不是每种文件都重新写一套检索切片算法

这比很多只会 `split(text, 500)` 的实现成熟得多。

---

### 3.4 PDF 为什么先转 Markdown 再切块

核心在 [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py)。

关键方法:

- `PDFParser.convert_markdown`
- `PDFParser.parse_into_chunks`

这里的处理不是“直接抽纯文本”，而是:

1. 用 `pymupdf4llm.to_markdown(...)` 把 PDF 转成 Markdown
2. `write_images=True` 把 PDF 中的图片导出
3. 把图片上传到 OSS
4. 重写 Markdown 中的图片链接
5. 再把 Markdown 文件交给 `markdown_parser.parse_into_chunks(...)`

这样做的好处很明显:

- 比直接抽纯文本更能保留版式结构
- 标题层级、段落结构、图片引用更容易保留
- 后面 chunk 时可以利用 Markdown 标题语义

面试里这是一个很好讲的工程点:

> PDF 解析最难的不是“读出字符”，而是尽量保留结构。这个项目把 PDF 先转成 Markdown，再按 Markdown 标题结构切块，本质上是在尽可能保留文档语义骨架。

---

### 3.5 Markdown 切块为什么比定长切分更合理

核心在 [markdown.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/markdown.py)。

这个类做了几件很值得讲的事:

- 用 `header_pattern = r'^(#{1,5})\\s+(.+)$'` 解析标题层级
- 维护 `current_headers`
- 生成 `header_path`，例如 `一级标题 > 二级标题 > 三级标题`
- 切块时把 `header_path` 拼进 chunk 内容
- 控制 `min_chunk_size`、`max_chunk_size`、`overlap_size`
- 切分长段落时会避开链接和图片语法边界

几个重要细节:

1. 不是只保留正文，还把标题路径一起塞进 chunk

这非常关键。因为向量检索时，如果 chunk 只有正文，没有章节语境，召回质量会下降。这个项目通过 `header_path + 正文` 的方式，把“局部内容”和“全局章节语义”绑定起来了。

2. 不是机械切分，而是尽量找安全切点

方法如:

- `find_link_boundaries`
- `is_safe_cut_position`
- `find_best_cut_position`
- `split_long_paragraph`

它会尽量避免把:

- Markdown 链接
- 图片语法
- 句子边界

从中间剪断。

3. 有 overlap

`overlap_size=128` 说明 chunk 之间有重叠区。这样能减少“关键信息刚好落在两个片段边界”导致的召回缺失。

面试里可以直接这么讲:

> 我们没有用简单定长切块，而是按 Markdown 标题层级切，保留 header path，并通过 overlap 和安全切点避免破坏句子、链接和图片结构，这会直接影响后续召回质量。

---

### 3.6 Chunk 摘要是怎么做的，为什么要有摘要向量

还是在 [parser.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/parser.py)。

如果配置 `app_settings.rag.enable_summary=True`，系统会额外执行:

- `DocParser.generate_summary`

实现特点:

- 通过 `asyncio.Semaphore(max_concurrent_tasks)` 控制并发
- 用 `ModelManager.get_conversation_model()` 调模型
- 对每个 chunk 生成一个较短摘要
- 最终把摘要写回 `chunk.summary`

这意味着每个 chunk 不只有:

- `content`

还有:

- `summary`

这样做的价值在于:

- 原文更完整，但可能噪声大
- 摘要更短，语义更集中

所以后面 Milvus 建索引时，项目同时建立了:

- 正文向量 `embedding`
- 摘要向量 `embedding_summary`

这是一种典型的“双通道召回”思路。

---

### 3.7 Milvus 是怎么建模的

核心在 [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py)。

关键方法:

- `create_collection`
- `insert`
- `search`
- `search_summary`
- `delete_by_file_id`

这个项目里，Milvus 不是一个大统一 collection，而是:

- 每个知识库 `knowledge_id` 对应一个 collection

也就是说，`collection_name` 直接用知识库 ID。

这会带来两个效果:

1. 数据隔离天然更强
2. 删除知识库或按知识库检索时逻辑更直接

#### 字段设计

`create_collection` 里定义的字段很有代表性:

- `chunk_id`
- `content`
- `embedding`
- `summary`
- `embedding_summary`
- `file_id`
- `file_name`
- `knowledge_id`
- `update_time`

这说明它不是只存向量，而是把检索结果回显所需的元信息也一起存了。

#### 为什么有两个向量字段

索引分别建在:

- `embedding`
- `embedding_summary`

对应两种检索模式:

- `search(...)` 走正文向量
- `search_summary(...)` 走摘要向量

这就是前面提到的“双通道召回”。

#### 索引参数

当前实现里用的是:

- `index_type: IVF_FLAT`
- `metric_type: L2`
- `nlist: 128`

搜索时:

- `nprobe: 16`

这里面试官很可能会追问:

> IVF_FLAT 是什么，nlist 和 nprobe 分别影响什么？

你可以这样回答:

- `IVF_FLAT` 是先聚类再在若干候选桶里做精确比对
- `nlist` 越大，聚类桶越细
- `nprobe` 越大，查询时扫描的桶越多，召回通常更高但更慢

再补一句:

> 这个项目的参数属于比较标准的初始工程配置，后续完全可以按数据规模和延迟目标做调优。

#### 懒加载集合

这个类还做了:

- `self.collections` 缓存 collection 对象
- `self.loaded_collections` 记录已 load 的集合
- `_get_collection_safe`
- `_ensure_collection_loaded`

这说明作者考虑过:

- collection 太多时不能每次都全量 load
- 首次访问再 load 更节省内存

这也是一个不错的面试加分点。

---

### 3.8 检索时不是只查 Milvus，而是支持混合检索

核心在 [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py) 和 [retrieval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/retrieval.py)。

主流程:

1. 查询重写
2. 混合召回
3. 去重
4. Rerank
5. TopK 过滤
6. 拼接结果

#### 第一步: Query Rewrite

入口:

- `RagHandler.query_rewrite`

它通过 `query_rewriter.rewrite(query)` 把用户问题改写成多个检索 query。

为什么这么做:

- 用户原问题可能太短
- 或者表达方式和文档写法不一致
- 多 query 能提高召回覆盖率

#### 第二步: 混合召回

`mix_retrival_documents(...)` 里做了两种路径:

- 开启 ES 时: `ES + Milvus`
- 没开 ES 时: `Milvus only`

这代表系统支持:

- 向量语义检索
- 关键词/倒排检索

它们结合后能兼顾:

- 语义相似
- 关键词精确命中

#### 第三步: 去重

源码按 `chunk_id` 去重:

- `seen_chunk_ids`

这样可以避免:

- 同一 chunk 被不同 query 召回多次
- 或同一 chunk 同时被 ES 和 Milvus 命中

#### 第四步: Rerank

核心在 [rerank.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/rerank.py)。

这里会把召回结果的 `content` 提交给专门的重排模型，然后返回更精准的排序分数。

这个阶段的意义是:

- 向量召回解决“找得到”
- rerank 解决“排得准”

这个区分面试里一定要说。

#### 第五步: summary 检索失败时回退到 content 检索

`rag_query_summary(...)` 里有个很好的兜底逻辑:

- 先按 `summary` 字段召回
- 如果召回数量不足 `top_k`
- 回退到 `content` 字段召回

这说明作者知道摘要虽然更聚焦，但也可能丢掉细节，所以做了降级。

这是很典型的“召回精度和召回覆盖率”的平衡。

---

### 3.9 这个知识库模块有哪些值得面试官认可的工程点

可以总结成 6 点:

1. 文档解析不是单纯抽文本，而是按格式做适配
2. PDF 先转 Markdown，保留结构信息
3. Chunk 不只是定长切分，而是利用标题层级和安全切点
4. 同时建立正文向量和摘要向量
5. 支持 ES + Milvus 混合检索
6. 在召回后再做 Rerank，提高最终上下文质量

如果你要更像“做过这套系统的人”，可以补一句:

> 这套实现的核心不是某个单点库，而是把文档结构保留、检索召回和最终上下文构造连成了一条完整链路。

---

## 4. MCP 协议、动态加载和插件式扩展是怎么做的

### 4.1 先讲原理: MCP 到底是什么

MCP 可以理解成 AI 时代的“工具接入标准协议”。

如果没有 MCP，每接一个外部工具都要自己写一套:

- 接口定义
- 参数协议
- 认证逻辑
- 返回格式适配

而 MCP 的目标是:

- 用统一协议描述工具
- 用统一会话机制调用工具
- 让 Agent 运行时动态发现和使用工具

你可以把它类比成:

- 前端时代的 OpenAPI
- 插件时代的统一插件协议
- AI Agent 时代的“工具总线”

---

### 4.2 这个项目为什么不只是“支持 MCP”，而是已经形成了可运营能力

从源码看，这个项目的 MCP 设计有四层:

1. 配置层: 描述 MCP Server 如何连接
2. 会话层: 根据 transport 建立 session
3. 加载层: 动态拉取远端 tool schema
4. 适配层: 把 MCP tool 包装成 LangChain tool

再往上还有:

5. 管理层: 持久化 MCP 服务、显示工具列表、用户自定义参数

这就不只是“能调用一下 MCP 服务”，而是已经能当作平台能力来管理。

---

### 4.3 支持哪些 MCP 连接方式

核心在 [sessions.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/sessions.py) 和 [mcp.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/schema/mcp.py)。

项目支持的 transport 类型有:

- `stdio`
- `sse`
- `streamable_http`
- `websocket`

对应的创建函数:

- `_create_stdio_session`
- `_create_sse_session`
- `_create_streamable_http_session`
- `_create_websocket_session`

统一入口:

- `create_session(connection)`

这段设计非常标准:

- 先看 `connection["transport"]`
- 再分发到对应 session 创建逻辑
- 如果缺少关键参数就抛异常

面试里你可以把这个设计总结为:

> 它把 MCP 的传输层差异封装到了 session factory，业务层只拿统一的 `ClientSession`，不关心底层到底是 stdio、SSE 还是 WebSocket。

这句话很重要，因为它体现了“协议抽象”和“业务无感”。

---

### 4.4 stdio / SSE / streamable_http / websocket 的区别该怎么讲

如果面试官追问，你可以这么回答:

- `stdio` 适合本地拉起进程型服务，常见于本地工具或命令行 MCP Server
- `sse` 适合基于 HTTP 的服务端推送型场景，实现简单
- `streamable_http` 本质上是更现代的 HTTP 流式 MCP 传输方案
- `websocket` 适合全双工、持续交互要求更强的服务

而这个项目的价值在于:

- 它没有把 MCP 接入写死在某一种连接协议上
- 而是把 transport 变成配置项

这意味着未来换服务端实现时，接入成本会低很多。

---

### 4.5 MCP 工具是怎么动态发现的

核心在 [multi_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/multi_client.py) 和 [tools.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/load_mcp/tools.py)。

关键方法:

- `MultiServerMCPClient.get_tools`
- `load_mcp_tools`
- `_list_all_tools`

#### `_list_all_tools(session)`

这个方法会:

- 调用 `session.list_tools(cursor=...)`
- 处理 `nextCursor`
- 分页把所有 MCP tools 拉全

这说明作者考虑到了:

- 工具列表可能很多
- MCP 服务端可能是分页返回

这不是“写个 demo 调一次 list_tools 就完了”的实现。

#### `load_mcp_tools(...)`

它会:

1. 拿到 MCP tool 列表
2. 把每个 MCP tool 转成 LangChain tool

转换函数是:

- `convert_mcp_tool_to_langchain_tool`

---

### 4.6 MCP Tool 是怎么被包装成 LangChain Tool 的

这是整个 MCP 接入最关键的一层。

在 [tools.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/load_mcp/tools.py) 中，`convert_mcp_tool_to_langchain_tool(...)` 做了几件事:

1. 把 MCP 的 `name` 变成 LangChain tool 名字
2. 把 MCP 的 `description` 变成 tool 描述
3. 把 `inputSchema` 直接作为 `args_schema`
4. 定义一个 `call_tool(**arguments)` 协程
5. 最终返回 `StructuredTool(...)`

这个设计的意义是:

- 对 Agent 来说，MCP 工具和本地 Python 工具在调用接口上被统一了
- 这样上层 Agent 根本不用知道“这个工具来自远端 MCP 服务器”

也就是:

> MCP 负责远程协议，LangChain Tool 负责本地 Agent 调度，两者通过适配层打通。

#### 为什么 `session=None` 时也能工作

这里还有个细节很值得讲:

如果没有传现成 `session`，工具执行时会:

- `async with create_session(connection) as tool_session`
- `await tool_session.initialize()`
- 再去 `call_tool`

也就是说:

- 工具定义阶段和工具执行阶段可以解耦
- 每次调用时按需创建会话

这是一种典型的 lazy session 模式。

优点:

- 不用长期持有很多远端连接
- 更适合多服务、低频调用的场景

代价:

- 单次调用有额外建连开销

这也是你可以主动补充的 trade-off。

---

### 4.7 多个 MCP Server 是怎么统一管理的

核心在 [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/manager.py)。

关键类:

- `MCPManager`

它上面封装了一个:

- `MultiServerMCPClient`

主要能力:

- `get_mcp_tools()`
- `show_mcp_tools()`
- `call_mcp_tools()`

#### `show_mcp_tools()`

这个方法不是只返回工具名，而是会收集:

- `tool.name`
- `tool.description`
- `tool.args_schema`

这就意味着前端或管理层可以展示:

- 这个 MCP Server 提供了什么工具
- 每个工具接受哪些参数

#### `call_mcp_tools()`

这里用了 `asyncio.gather(...)` 并发执行多个工具调用。

说明项目不仅支持“发现工具”，也支持“并发调工具”。

面试里可以说:

> MCPManager 对下统一连接多个 MCP Server，对上暴露统一的工具发现和并发执行接口，相当于平台内部的 MCP 编排层。

---

### 4.8 自定义 MCP Server 是怎么接入系统的

核心入口在 [mcp_server.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/v1/mcp_server.py) 和 [mcp_server.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/mcp_server.py)。

创建 MCP Server 的流程大致是:

1. 前端传入 `imported_config`
2. 服务端先 `validate_imported_config(...)`
3. 从 `mcpServers` 中解析出 server 信息
4. 转成内部 MCP 配置
5. 构造 `MCPManager`
6. 动态拉取该服务的工具列表
7. 用结构化输出 Agent 自动生成 `mcp_as_tool_name` 和 `description`
8. 持久化到数据库

这里最有意思的是第 7 步。

项目不是让开发者手工给每个 MCP Server 写“平台展示名”和“描述文案”，而是用:

- `StructuredResponseAgent(MCPResponseFormat)`
- `McpAsToolPrompt`

基于工具列表，自动生成:

- `mcp_as_tool_name`
- `description`

这是一种很聪明的产品化设计:

- 接入一个新 MCP Server 后
- 平台能自动生成更适合 Agent 使用的工具描述

换句话说，这里已经带了一点“自描述、自适配”的味道。

---

### 4.9 用户级 MCP 参数配置是怎么做的

核心在 [mcp_user_config.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/mcp_user_config.py)。

关键方法:

- `get_mcp_user_config`

它会把数据库中保存的配置列表:

- `[{key, label, value}, ...]`

转成运行时真正使用的参数字典:

- `{key: value}`

这意味着:

- 平台可以保存“每个用户对某个 MCP Server 的个性化配置”
- 运行时 Agent 调该 MCP 工具前，可以注入这些个性化参数

实际调用位置在多个 Agent 里都出现了，比如:

- `simple_agent.py`
- `wechat_agent.py`
- `mcp_agent.py`
- `lingseek/agent.py`

这个点非常像插件系统里的“实例级配置”。

所以你可以把这块总结成:

> 项目不仅实现了 MCP Server 的动态接入，还实现了 MCP Server 的用户级配置注入，这使它更像一个可扩展平台，而不是写死工具的单体应用。

---

### 4.10 这套 MCP 设计的本质价值

本质上它解决了三个问题:

1. 工具接入标准化
2. 工具发现动态化
3. 工具扩展平台化

如果你面试时想讲得高级一点，可以说:

> 传统做法是“工具直接写死在代码里”，而 MCP 的价值是把“工具能力”从代码编译期绑定，变成运行时可发现、可配置、可扩展的外部能力。

这句话一般面试官会比较认可。

---

## 5. 多模型切换、记忆、思维可视化和参数管理是怎么做的

### 5.1 先讲原则: 为什么 AI 系统不能只有一个模型

很多项目一上来只接一个聊天模型，但真实系统里，不同任务对模型要求不一样:

- 普通对话，需要自然语言生成能力
- 工具调用，需要函数调用稳定性
- 深度推理，需要 reasoning 模型
- RAG 检索，需要 embedding 模型
- 排序，需要 rerank 模型

所以更合理的架构是“按任务拆模型角色”。

这个项目在这方面做得比较明确。

---

### 5.2 模型管理中心是怎么设计的

核心在 [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/models/manager.py)。

关键类:

- `ModelManager`

它不是只返回一个默认模型，而是区分了多个模型入口:

- `get_conversation_model()`
- `get_tool_invocation_model()`
- `get_reasoning_model()`
- `get_lingseek_intent_model()`
- `get_qwen_vl_model()`
- `get_user_model(**kwargs)`
- `get_embedding_model()`

这说明系统架构层面已经明确区分:

- 对话生成模型
- 工具调用模型
- 推理模型
- 多模态模型
- 用户自定义模型
- 向量化模型

#### 为什么这很重要

因为一个模型很难同时在这几方面都最优:

- 会聊天的不一定最适合 function call
- 会推理的不一定最便宜
- 会生成的不一定能做 embedding

所以 `ModelManager` 本质上是模型路由层。

---

### 5.3 “多模型无缝切换”在这个项目里具体体现在哪里

主要有两层:

#### 第一层: 后端统一抽象

通过 `ModelManager`，业务代码不直接关心某个厂商 SDK，而是关心:

- 我要的是 conversation model
- 还是 reasoning model
- 还是 embedding model

也就是说，业务逻辑绑的是“能力角色”，不是“具体供应商”。

#### 第二层: 用户可见模型管理

核心在 [llm.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/v1/llm.py) 和 [llm.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/llm.py)。

项目提供了:

- 创建模型
- 更新模型
- 删除模型
- 查询可见模型
- 按名称搜索模型

`LLMService.get_visible_llm(user_id)` 会把:

- 用户自己的模型
- 系统内置模型

一起返回，并按类型分组:

- `LLM`
- `Embedding`
- `Reranker`

这说明前端可以动态展示当前用户可用的模型生态，而不是前端写死几个选项。

前端对应页面在 [model.vue](/e:/Codes/study-projects/AgentChat/src/frontend/src/pages/model/model.vue)。

从这个页面可以看出，至少支持配置:

- `model`
- `api_key`
- `base_url`
- `provider`
- `llm_type`

所以这里的“多模型无缝切换”，本质上是:

- 模型配置数据化
- 模型选择运行时化
- 模型角色分层化

---

### 5.4 上下文记忆是怎么做的

核心在 [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)。

关键类:

- `AsyncMemory`

这里一定要讲清楚:

- 这个项目的“知识库”不是“记忆”
- 知识库主要存文档知识
- 记忆主要存用户/会话/运行过程中的事实和偏好

也就是说，这是两套用途不同的 retrieval 系统。

#### 初始化时用了什么

`AsyncMemory.__init__` 中:

- `self.embedding_model = ModelManager.get_embedding_model()`
- `self.vector_store = VectorStoreManager.get_chroma_vector()`
- `self.llm = ModelManager.get_conversation_model()`

这里有个很容易被忽略但很重要的点:

> 记忆默认走的是 `Chroma` 向量存储，不是知识库那套 `Milvus`。

这说明项目做了职责分离:

- 知识库检索: 偏文档级、规模化、独立 collection 管理
- 记忆检索: 偏会话级、用户级、快速存取

#### 记忆的作用域控制

通过 `_build_filters_and_metadata(...)` 构建:

- `user_id`
- `agent_id`
- `run_id`
- `actor_id`

这非常重要，因为记忆不能乱召回。

比如:

- 用户 A 的偏好不能给用户 B
- 一个会话的临时事实不一定该跨会话共享
- 某个 agent 的 procedural memory 不一定给别的 agent 用

所以这套过滤条件，本质上是在做“记忆隔离”。

---

### 5.5 记忆不是机械存消息，而是先抽取事实

这是 `AsyncMemory.add(...)` 最值得讲的地方。

如果 `infer=True`，它不会把整段对话原样存入向量库，而是:

1. 先 `parse_messages(messages)`
2. 构造事实抽取 prompt
3. 调 LLM 提取 `facts`
4. 对每条 fact 先做 embedding
5. 去向量库里查相似历史记忆
6. 再让 LLM 判断这条新事实应该:
   - `ADD`
   - `UPDATE`
   - `DELETE`
   - `NONE`
7. 最后再真正写库

这套流程的本质是:

- 记忆存储不是 append-only
- 而是“知识状态维护”

举个例子:

- 旧记忆: “用户喜欢 Java”
- 新对话: “我现在主要写 Go，不怎么写 Java 了”

如果只追加，会越存越乱。

而这个项目的设计目标是:

- 尽量让记忆保持最新、可用、一致

这在面试里是一个明显的亮点。

你可以这样讲:

> 我们的记忆不是简单把聊天记录向量化，而是先让模型抽取事实，再对比历史记忆，决定增删改，这样记忆更像结构化用户画像，而不是聊天日志。

---

### 5.6 记忆是怎么检索的

核心方法:

- `AsyncMemory.search(...)`
- `_search_vector_store(...)`

流程是:

1. 对 query 生成 embedding
2. 带着 `user_id/agent_id/run_id/actor_id` 过滤条件去向量库查
3. 取回 payload
4. 组装成带 `score` 的记忆结果
5. 根据 `threshold` 过滤

这里要注意两个面试点:

1. 记忆检索有向量相似度，也有 metadata filter

这说明不是单纯语义相似，还做了会话范围约束。

2. 返回的不只是 memory text，还有 metadata

例如:

- `role`
- `actor_id`
- `user_id`
- `run_id`

这有利于后续做更细的上下文注入。

---

### 5.7 思维过程可视化是怎么做的

这个能力主要体现在 `Mars` 相关模块。

核心后端在 [mars_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mars/mars_agent.py)。

核心前端在 [mars-chat.vue](/e:/Codes/study-projects/AgentChat/src/frontend/src/pages/mars/mars-chat.vue)。

#### 后端做了什么

`MarsAgent` 同时准备了三类模型:

- `conversation_model`
- `tool_invocation_model`
- `reasoning_model`

在 `ainvoke_stream(...)` 里，它把两个流并行组织起来:

1. `run_reasoning_model()`
2. `run_mars_agent()`

其中 `run_reasoning_model()` 会持续读取 reasoning model 的流式输出，并区分:

- `delta.reasoning_content` -> 发成 `reasoning_chunk`
- `delta.content` -> 发成 `response_chunk`

如果工具链已经开始产出结果，它还会通过 `self.is_call_tool` 和 `reasoning_interrupt` 做中断和切换，避免推理流和工具结果互相污染。

这说明“思维可视化”不是前端随便加个折叠面板，而是后端事件流里真的区分了:

- 思考内容
- 最终回答内容

#### 前端做了什么

`mars-chat.vue` 里会识别:

- `reasoning_chunk`
- `response_chunk`

并把 `reasoning_chunk` 渲染成可折叠的 thinking segment。

所以这个功能的本质是:

- 后端事件协议层面把“思维”和“回答”拆开
- 前端展示层面再把它可视化

面试里可以总结成:

> 这个项目的思维过程可视化不是对最终答案做二次拆分，而是模型流式输出阶段就把 reasoning token 和 answer token 分通道传给前端。

---

### 5.8 精细化参数调优体现在哪里

这块可以从两个层面讲。

#### 第一层: 模型配置参数数据化

从模型管理页和后端接口看，至少支持配置:

- `model`
- `provider`
- `base_url`
- `api_key`
- `llm_type`

这使得团队可以方便切换:

- 供应商
- 模型名称
- 接口域名
- 模型类别

#### 第二层: 检索与召回参数可调

在 RAG 侧还能看到不少策略参数:

- `min_chunk_size`
- `max_chunk_size`
- `overlap_size`
- `top_k`
- `min_score`
- `enable_summary`
- `enable_elasticsearch`
- Milvus `nlist`
- Milvus `nprobe`

也就是说，这个系统的“精细化参数调优”不只是模型 API 参数，而是贯穿:

- 文档切块
- 向量检索
- 混合召回
- Rerank 过滤

如果面试官问“你们的参数调优都调了什么”，你就不要只回答 temperature 之类通用参数，要从整条链路讲。

---

## 6. 三块能力之间是怎么协同的

这三块能力并不是孤立的。

### 6.1 知识库和 Agent 的关系

知识库模块负责提供:

- 可检索外部知识

Agent 在需要时可以:

- 先做检索
- 再把检索结果拼到上下文里
- 最后生成回答

所以知识库是 Agent 的“外部知识供给层”。

### 6.2 MCP 和 Agent 的关系

MCP 模块负责提供:

- 可动态发现和调用的外部工具

所以 MCP 是 Agent 的“外部行动能力层”。

### 6.3 记忆和 Agent 的关系

记忆模块负责提供:

- 用户历史偏好
- 会话上下文事实
- 长期或短期状态

所以记忆是 Agent 的“个性化上下文层”。

### 6.4 多模型管理的关系

多模型模块负责提供:

- 针对不同任务选择不同模型

所以多模型是整个系统的“模型调度层”。

最终可以把它们概括成一张思维图:

- RAG: 负责找知识
- MCP: 负责调工具
- Memory: 负责记住用户和上下文
- Multi-Model: 负责给不同任务配合适模型

这套分层在面试里是很值得讲的。

---

## 7. 你可以直接对面试官怎么讲

如果面试官让你概括这三部分，可以这样说:

> 这个项目在 AI 应用架构上分成了四层。第一层是 RAG 知识层，负责把 PDF、Markdown、Docx 等文件解析成 chunk，建立 Milvus 向量索引，并通过 query rewrite、混合检索和 rerank 提供高质量上下文。第二层是 MCP 工具层，支持 stdio、SSE、streamable_http 和 websocket 等多种传输方式，把远程 MCP 服务动态加载成 LangChain Tool，形成插件式扩展能力。第三层是记忆层，用向量存储保存用户事实和会话记忆，并且不是简单追加，而是通过 LLM 决定 ADD、UPDATE、DELETE。第四层是模型调度层，把对话模型、工具调用模型、推理模型、embedding 模型和 rerank 模型分角色管理。这样 Agent 在运行时既能查知识、又能调工具、还能利用记忆和不同模型协同工作。 

如果需要更短版本:

> 这个项目的核心不是单个模型回答问题，而是把知识检索、工具调用、用户记忆和模型路由拆成独立能力层，再由 Agent 在运行时编排它们。

---

## 8. 面试题与参考答案

### 题 1: 为什么知识库切块不能简单按固定长度切分？

参考答案:

因为固定长度切分很容易破坏语义边界，比如把一个章节说明、列表或链接从中间截断，导致向量表示不稳定、召回不准。这个项目在 [markdown.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/markdown.py) 中按 Markdown 标题层级切分，并保留 `header_path`，同时通过 `find_best_cut_position` 避免切断链接和图片语法，还设置了 overlap，召回质量会明显更稳定。

### 题 2: 这个项目为什么把 PDF 先转成 Markdown？

参考答案:

因为 PDF 的难点不是提取字符，而是保留结构。项目在 [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py) 里用 `pymupdf4llm.to_markdown(...)` 转换，并导出图片、上传 OSS、重写 Markdown 图片链接，再交给 Markdown chunker 处理。这样比直接抽纯文本更能保留标题层级和文档结构。

### 题 3: 为什么 Milvus 里同时存 `embedding` 和 `embedding_summary`？

参考答案:

因为正文和摘要适合不同的召回策略。正文信息更完整，但可能噪声大；摘要更短、更聚焦，适合先做高层语义召回。这个项目在 [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py) 中给正文和摘要各建了一个向量字段，对应 `search` 和 `search_summary` 两条检索路径。

### 题 4: 向量召回和 Rerank 的职责有什么区别？

参考答案:

向量召回解决的是“找得到”，它会快速从大规模候选集中筛出语义相近片段；Rerank 解决的是“排得准”，它会对召回结果做更细粒度的相关性重排。这个项目在 [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py) 中先混合召回，再调用 [rerank.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/rerank.py) 的重排模型。

### 题 5: 这个项目为什么要做 Query Rewrite？

参考答案:

用户问题的表达方式未必和文档里的措辞一致，直接检索可能召回不足。Query Rewrite 可以把原问题扩成多个语义相近但表述不同的查询，提高召回覆盖率。项目里由 `RagHandler.query_rewrite` 负责这一步。

### 题 6: MCP 在这个项目里到底起什么作用？

参考答案:

MCP 在这里充当统一工具接入协议。项目不是把工具一条条写死，而是通过 MCP 动态连接远端服务，读取工具列表，再包装成 LangChain Tool 给 Agent 使用。这样接新工具时，不需要重写大量业务代码，只要配置新的 MCP Server 即可。

### 题 7: 这个项目支持哪些 MCP 连接方式？为什么要支持多种？

参考答案:

支持 `stdio`、`sse`、`streamable_http`、`websocket`，定义在 [sessions.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/sessions.py)。支持多种传输方式的意义在于，不同 MCP Server 的部署形态不同，有的是本地进程，有的是 HTTP 服务，有的是长连接服务。如果把接入方式写死，系统扩展性会很差。

### 题 8: MCP Tool 为什么还要再转换成 LangChain Tool？

参考答案:

因为上层 Agent 编排逻辑使用的是 LangChain/LangGraph 工具体系。项目通过 `convert_mcp_tool_to_langchain_tool(...)` 把 MCP 的 `name`、`description`、`inputSchema` 和 `call_tool` 能力包装进 `StructuredTool`，这样上层 Agent 不需要知道它来自远端 MCP 还是本地 Python 函数。

### 题 9: 这个项目的“插件化”体现在哪里？

参考答案:

插件化主要体现在 MCP Server 的动态接入。前端上传 `imported_config` 后，后端会校验配置、建立连接、动态读取该 MCP Server 提供的工具、生成可展示的工具描述，并持久化。也就是说，系统功能不是静态编译进代码里的，而是可以运行时扩展。

### 题 10: 为什么 AI 系统里要区分 conversation model 和 tool invocation model？

参考答案:

因为聊天生成和函数调用是两种不同优化目标。聊天模型关注语言质量，工具调用模型更关注结构化输出稳定性和工具参数填充准确率。项目在 [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/models/manager.py) 中把它们拆开，说明架构层面已经在做按任务路由。

### 题 11: 记忆系统为什么不能简单把聊天记录全量向量化？

参考答案:

因为聊天记录里有大量噪声、重复信息和过期信息。这个项目在 [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py) 里先用 LLM 从消息中抽取 facts，再与历史记忆比对，最后决定 `ADD/UPDATE/DELETE/NONE`。这样记忆更接近结构化事实库，而不是原始日志仓库。

### 题 12: 记忆系统和知识库系统有什么区别？

参考答案:

知识库存的是外部文档知识，通常规模更大、以文件和 chunk 为中心；记忆系统存的是用户偏好、会话上下文和运行中沉淀出的事实，通常以 `user_id/agent_id/run_id` 为过滤维度。这个项目里知识库主要走 Milvus，记忆默认走 Chroma，也体现了两者职责不同。

### 题 13: 思维过程可视化为什么不只是前端问题？

参考答案:

因为如果后端不区分“推理内容”和“最终回答”，前端就无从可视化。项目在 [mars_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mars/mars_agent.py) 中把 reasoning model 的 `reasoning_content` 发成 `reasoning_chunk`，把正式回答发成 `response_chunk`，前端 [mars-chat.vue](/e:/Codes/study-projects/AgentChat/src/frontend/src/pages/mars/mars-chat.vue) 再按 chunk 类型渲染折叠的 thinking 区域。

### 题 14: 如果让你继续优化这个项目的 RAG，你会怎么做？

参考答案:

我会从四个方向优化。第一，给 chunk 增加更丰富的 metadata，比如章节号、页码、标题路径单独字段。第二，Milvus 检索策略可以按数据量切换更合适的索引类型，并调优 `nlist/nprobe`。第三，混合检索的权重可以做更细的融合，而不是简单拼接再去重。第四，可以把召回结果做引用定位，让回答支持 chunk 级出处回溯。

### 题 15: 如果让你继续优化这个项目的 MCP 架构，你会做什么？

参考答案:

我会补三类能力。第一，做连接池或 session 复用，降低频繁建连成本。第二，增加 tool 调用级别的超时、熔断和重试。第三，把 MCP tool 的 schema 和可用性缓存起来，减少每次都全量探测服务器的开销。

---

## 9. 面试时最容易被追问的几个细节

### 9.1 为什么说知识库和记忆是两套系统

因为它们解决的问题不同:

- 知识库解决“模型不知道企业文档”
- 记忆解决“模型记不住当前用户和上下文”

一个偏外部事实，一个偏交互状态。

### 9.2 为什么多模型管理本质是模型路由

因为业务代码不该直接绑定某个具体模型，而应该绑定能力角色。系统运行时再决定:

- 谁负责聊天
- 谁负责工具调用
- 谁负责推理
- 谁负责 embedding

### 9.3 为什么 MCP 比自己写一堆 HTTP 接口更适合 Agent 系统

因为 MCP 把:

- 工具描述
- 参数 schema
- 调用协议
- 资源与 prompt 能力

都统一到了标准里，更适合做运行时动态发现和编排。

---

## 10. 最后给你的复述模板

你可以把这三部分压成下面这段回答:

> 这个项目在 AI 架构上做了比较完整的分层。知识库侧，它先把 PDF、Docx、Markdown 等文档解析成结构化 chunk，再把正文和摘要分别向量化写入 Milvus，查询时会做 query rewrite、混合检索、去重和 rerank，最后把高质量片段拼给模型。工具侧，它通过 MCP 协议把外部服务接成标准化工具，支持 stdio、SSE、streamable_http 和 websocket 等多种连接方式，并把 MCP tool 动态转换成 LangChain Tool，因此系统能像插件一样扩展能力。模型侧，它把对话模型、工具调用模型、推理模型、embedding 模型和 rerank 模型拆开管理，同时还有独立记忆系统，能够按用户、会话和 agent 维度保存和检索事实记忆，并支持思维过程流式可视化。所以这不是一个单模型聊天应用，而是一个具备知识、工具、记忆和模型路由能力的 Agent 平台。 

如果你还要更像“实战经验”，最后补一句:

> 真正难的不是把这些组件接上，而是把它们之间的数据边界和职责边界设计清楚，这个项目在这方面已经有比较明显的工程化意识。

