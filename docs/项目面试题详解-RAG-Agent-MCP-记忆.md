# 项目面试题详解: RAG、Agent、MCP、记忆与容灾

## 1. 说明

这份文档专门回答一组偏实战的 AI 项目面试题。

回答原则:

- 能结合这个项目源码的，尽量结合具体实现回答
- 项目里没有明确实现的，不会硬说做过，会明确标注“项目未完整落地”
- 尽量讲原理、讲取舍、讲代码细节，但不贴大段完整代码

为了便于你背诵，我会尽量按“面试可直接回答”的风格来写。

---

## 2. RAG 相关

### 2.1 RAG 中 chunk 怎么分的？

这个项目的 chunk 不是简单一刀切的定长切分，而是“按文档结构优先”的切分。

核心入口在:

- [parser.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/parser.py)
- [markdown.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/markdown.py)
- [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py)

整体流程是:

1. 先按文件类型分发解析器
2. PDF 先转 Markdown
3. 再按 Markdown 标题层级切块
4. 每个 chunk 会带上 `header_path`
5. 对超长段落做安全切分
6. chunk 之间保留 overlap

#### 具体细节

`DocParser.parse_doc_into_chunks(...)` 会根据后缀路由到不同 parser:

- `md` -> `markdown_parser`
- `pdf` -> `pdf_parser`
- `docx` -> `docx_parser`
- `txt` -> `text_parser`
- 图片、Excel、其他文本格式会先转 txt 再处理

PDF 处理不是直接抽纯文本，而是在 [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py) 里用 `pymupdf4llm.to_markdown(...)` 转成 Markdown，再把图片上传 OSS、重写图片链接，最后走 Markdown parser。

真正的 chunk 逻辑在 `MarkdownParser` 里:

- `min_chunk_size = 256`
- `max_chunk_size = 512`
- `overlap_size = 128`

它会:

- 用正则 `^(#{1,5})\\s+(.+)$` 识别标题
- 构造 `header_path`，例如 `产品介绍 > 架构设计 > 缓存模块`
- 把 `header_path + 正文` 作为 chunk 内容
- 对长段落尽量按句子边界切
- 用 `find_link_boundaries` / `is_safe_cut_position` 避免把 Markdown 链接、图片语法从中间切断

#### 面试里可以怎么说

> 我们没有用简单的定长切块，而是优先保留文档结构。PDF 先转 Markdown，再按标题层级切块，把章节路径一起写入 chunk 内容，同时设置 overlap，避免边界信息丢失。这样对召回质量会明显更友好。

---

### 2.2 用的什么 embedding 模型？

这个项目默认 embedding 模型配置在:

- [config.yaml](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/config.yaml)

从当前配置看，默认是:

- `text-embedding-v4`

对应配置项:

- `app_settings.multi_models.embedding.model_name`
- `app_settings.multi_models.embedding.base_url`
- `app_settings.multi_models.embedding.api_key`

Embedding 调用入口在:

- [embedding.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/embedding.py)
- [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/models/manager.py)

RAG 检索使用的是 `services/rag/embedding.py` 中的 `get_embedding(...)`，底层通过 `AsyncOpenAI(...).embeddings.create(...)` 调兼容 OpenAI 的 embedding 接口。

它还做了一个小优化:

- 如果输入不超过 10 条，直接一次请求
- 超过 10 条就分 batch
- 并通过 `asyncio.Semaphore(5)` 限制并发

这说明作者考虑过 embedding 批量请求的吞吐和限流。

#### 面试里可以这样答

> 项目默认配置的是阿里兼容 OpenAI 接口的 `text-embedding-v4`。Embedding 统一通过 OpenAI-compatible API 调用，代码里还做了 batch 和并发控制，避免一次性大批量嵌入把接口打爆。

---

### 2.3 召回策略是什么？

这个项目的召回策略不是单一路径，而是“多阶段混合召回”。

主逻辑在:

- [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py)
- [retrieval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/retrieval.py)
- [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py)
- [es_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/es_client.py)
- [rerank.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/rerank.py)

完整链路大致是:

1. Query Rewrite
2. 向量检索 / 混合检索
3. 去重
4. Rerank
5. 阈值过滤
6. 拼接上下文

#### 第一层: Query Rewrite

`RagHandler.query_rewrite(...)` 会先把用户 query 改写成多个检索 query。

这么做的目的是:

- 提高召回覆盖率
- 缓解用户表达和文档措辞不一致的问题

#### 第二层: Summary / Content 双路召回

Milvus collection 里同时有两个向量字段:

- `embedding`
- `embedding_summary`

对应两个接口:

- `search(...)` 查正文向量
- `search_summary(...)` 查摘要向量

`rag_query_summary(...)` 会优先按 summary 查，如果结果不足，再回退到 content 检索。

#### 第三层: ES + Milvus 混合召回

如果 `enable_elasticsearch=True`，项目会同时用:

- ES 做关键词检索
- Milvus 做语义检索

然后把结果合并。

这其实就是典型的 hybrid retrieval:

- ES 擅长精确关键词命中
- Milvus 擅长语义相似

#### 第四层: 去重

源码按 `chunk_id` 去重，避免:

- 同一 chunk 被多个 query 重复召回
- 同一 chunk 同时被 ES 和 Milvus 命中

#### 第五层: Rerank

最终会调用独立 rerank 模型对召回结果重排，而不是直接把向量相似度最高的 chunk 拼给模型。

#### 面试里可以这样说

> 我们不是单纯 top-k 向量检索，而是 Query Rewrite + Summary/Content 双路召回 + ES/Milvus 混合检索 + chunk 去重 + Rerank 的多阶段召回链路。这样做的目的是同时兼顾召回覆盖率和排序准确率。

---

### 2.4 怎么评估检索的准确率？

这个问题要分成两个层次回答:

#### 第一层: 检索本身怎么评估

如果只评检索，不看生成回答，常见指标是:

- Recall@K
- Precision@K
- MRR
- nDCG
- Hit Rate

意思分别是:

- `Recall@K`: 正确片段有没有被召回到前 K 个
- `Precision@K`: 前 K 个里有多少是真正相关片段
- `MRR`: 第一个正确结果排得有多靠前
- `nDCG`: 综合考虑相关性等级和排序位置

#### 第二层: RAG 端到端怎么评估

如果不仅评检索，还评最终回答，可以用:

- Context Precision
- Context Recall
- Faithfulness
- Answer Relevancy

这个项目里其实已经有一个评估脚本:

- [eval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/eval.py)

它用了 `ragas.evaluate(...)`，指标包括:

- `context_precision`
- `context_recall`
- `faithfulness`
- `answer_relevancy`

所以从项目角度可以说:

> 项目里有基于 RAGAS 的离线评估脚本，能同时评估上下文召回质量和最终回答质量。

---

### 2.5 有没有做过这方面的评估？

实事求是地说:

- 项目里有评估脚本
- 但从源码看，更像是实验性或离线评估样例
- 不是完整接入生产评测平台的那种持续评估体系

证据在 [eval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/eval.py):

- 它读取 `test.csv`
- 构造 question / ground_truth / context / answer
- 跑 `RAGAS evaluate`
- 最后输出到 Excel

这说明:

- 至少做过离线评估思路验证
- 但看不出已经形成系统化 benchmark 平台

#### 面试推荐说法

> 项目里已经有基于 RAGAS 的离线评估脚本，说明我们有做 Context Precision、Context Recall、Faithfulness、Answer Relevancy 这类指标评估。不过从落地程度看，更偏离线验证，不算完整的线上持续评估体系。如果继续做，我会补固定测试集、版本化评测和回归评估流水线。

---

### 2.6 关于 RAG 检索前的数据处理: 你是如何处理数据的？

这个问题非常适合结合项目讲，因为这个项目的数据预处理做得还不错。

答案不是“一刀切”，而是“先按格式适配，再统一落到结构化 chunk”。

#### 处理方式

- PDF: 先转 Markdown
- DOCX: 转 PDF 或再落到 Markdown 路径
- Markdown: 直接按标题结构解析
- TXT/HTML/CSV/JSON: 转文本后走 text parser
- Excel: 转 txt
- 图片: OCR/转 txt 后再走切块

也就是说，项目倾向于把多种异构文档最终归一到:

- 结构化 Markdown
- 或可切块文本

而不是对所有格式都简单做 `split(500)`

#### 为什么这么做

因为 RAG 的瓶颈很多时候不在“模型”，而在“文档有没有被正确结构化”。

如果你一刀切:

- 标题会丢
- 段落边界会乱
- 表格和图片语境会丢
- 语义上下文会被破坏

所以这个项目明显走的是“尽量保留结构”的路线。

---

### 2.7 RAG，为什么选 Chroma 而不是 Qdrant 或者 Milvus？

这个问题一定要先纠正一个事实:

#### 在这个项目里，知识库 RAG 并没有选 Chroma

知识库主路径用的是:

- `Milvus`

证据在:

- [knowledge_file.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/knowledge_file.py)
- [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py)
- [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py)

#### Chroma 用在哪里

Chroma 默认用在“记忆系统”里，不是知识库主路径。

证据在:

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)
- [vector_stores/__init__.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/vector_stores/__init__.py)

`AsyncMemory.__init__` 默认:

- `self.vector_store = VectorStoreManager.get_chroma_vector()`

#### 如果面试官问“为什么记忆用 Chroma，不用 Qdrant/Milvus？”

可以这样答:

> 这个项目里知识库走 Milvus，记忆走 Chroma，本质是按场景选型。Milvus更适合知识库这种文档规模更大、需要独立 collection 和 ANN 检索优化的场景；Chroma 对记忆这类会话级、用户级、小规模高频读写场景更轻量，工程接入成本也低。Qdrant 也是很好的选择，但这个项目当前没有落地 Qdrant。

---

### 2.8 不上 GraphRAG 的原因是什么？传统 RAG 混合检索的局限是什么？

这个项目里没有真正落地 GraphRAG。

甚至在记忆模块里还能看到:

- `self.enable_graph = False`
- `self.graph = None`

位置在 [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)。

所以这题要实事求是:

#### 项目没上 GraphRAG 的直接原因

从源码状态看，更像是:

- 当前还是以传统 chunk-based RAG 为主
- 图谱能力预留了接口，但未启用

#### 如果从工程取舍解释，合理原因通常有 4 个

1. 建图成本高

GraphRAG 一般要做:

- 实体抽取
- 关系抽取
- 图存储
- 图检索和路径推理

实现复杂度远高于传统 RAG。

2. 文档类型不一定适合图谱化

如果文档更多是:

- 操作文档
- 技术说明
- API 文档

传统 chunk + hybrid retrieval 往往已经足够。

3. 图谱质量很依赖抽取质量

实体和关系抽错，后面整条图推理都可能偏。

4. 维护成本更高

文档更新后:

- chunk 重建比较直接
- 图谱增量更新就复杂很多

#### 传统 RAG 混合检索的局限

也要坦诚说出来:

- 对跨 chunk 的全局关系建模弱
- 很难回答“实体 A 和 B 在多个文档中的关系链条”
- 多跳推理能力弱
- 对复杂组织结构、依赖网络这类信息不如图结构自然

#### 面试推荐说法

> 这个项目目前没有真正上 GraphRAG，主路径还是传统 RAG + Hybrid Retrieval。原因主要是工程复杂度、维护成本和场景适配性。传统 RAG 的局限在于它擅长局部片段召回，但对跨文档、多跳关系和实体关系链的表达不如图结构自然。如果后续场景更偏实体关系推理，再考虑上 GraphRAG 才更划算。

---

## 3. Agent 架构相关

### 3.1 ReAct 进入死循环怎么办？

这个项目确实主要使用的是 ReAct 风格的 Agent，但也有一些“防死循环”措施，只是不是所有地方都做得很彻底。

#### 项目里已有的控制手段

1. 工具调用并发限制

在:

- [mars_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mars/mars_agent.py)
- [wechat_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/workspace/wechat_agent.py)

里用了:

- `ToolCallLimitMiddleware(thread_limit=1)`

这至少能避免工具调用线程无限扩散。

2. DeepSearch 有显式 loop 上限

在:

- [stream_graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/stream_graph.py)
- [graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/graph.py)

都有:

- `research_loop_count`
- `max_research_loops`

这属于比较标准的 graph loop guard。

3. 某些场景有超时与取消

例如 [wechat_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/workspace/wechat_agent.py) 中对 `react_agent_task` 用了 `asyncio.wait_for(..., timeout=1.0)` 和 `cancel()`

这是一种粗粒度防挂死方式。

#### 但也要诚实说明

在普通 ReAct Agent 主路径里，并没有看到非常完整的:

- 最大 tool step 限制
- 最大 model turn 限制
- 重复工具调用检测
- 重复 observation 检测
- 终止判定器

也就是说，这部分还有提升空间。

#### 如果面试官问“你会怎么处理？”

建议回答成“项目现状 + 我的改进方案”:

> 项目里已经有 loop count、tool thread limit 和部分 timeout/cancel 机制，但如果担心 ReAct 死循环，我还会补 5 类控制：第一，限制最大 agent step；第二，限制同一工具在相同参数下的重复调用次数；第三，检测连续几轮 observation 没有信息增益时强制收敛；第四，给工具和模型都加超时与 fallback；第五，对长链任务转成 graph/plan 模式，不让 ReAct 无约束地自己试探。

---

### 3.2 为什么没考虑做长期记忆呢？

这个问题要先拆开。

#### 严格说，这个项目不是完全没有长期记忆

因为它确实有一个持久化的 memory vector store:

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)

而且按:

- `user_id`
- `agent_id`
- `run_id`

去存储和检索，这已经具备长期保留的能力。

#### 但它没有做“完整意义上的长期记忆体系”

比如没有明显看到这些能力:

- 多层记忆衰减策略
- 长短期记忆自动迁移
- 用户画像专门 schema
- 记忆重要性评分
- 记忆生命周期管理
- 长期记忆压缩与总结机制

所以更准确的说法是:

> 项目有持久化记忆，但不是完整分层的长期记忆架构。

#### 为什么可能没有进一步做重型长期记忆

这通常是个工程权衡:

1. 长期记忆容易脏

用户偏好会变，旧事实会过期。

2. 维护成本高

需要做:

- 记忆更新
- 冲突消解
- 重要性判断
- TTL 或衰减

3. 很多场景只需要会话级记忆 + 知识库就够了

尤其是工具型 Agent，不一定需要非常复杂的长期人格记忆。

#### 面试推荐说法

> 项目里其实已经有持久化 memory store，但更偏事实记忆，不算完整的长期记忆体系。之所以没有做更重的长期记忆分层，主要是因为长期记忆最难的不是存，而是更新、去噪、冲突消解和价值判断。当前项目优先保证知识库和工具调用主链路稳定，长期记忆属于下一阶段优化方向。

---

### 3.3 为什么用 ReAct 模式，不用 Plan-and-Execute 或其他 Agent 架构？

这个问题要结合项目现状回答。

#### 先说结论

这个项目并不是“只会 ReAct”。

它实际上是多种架构混用:

- 普通对话/工具调用主路径偏 `ReAct`
- `DeepSearch` 偏 `Graph + Reflection Loop`
- `LingSeek` 偏 `任务图分解 + 步骤执行`

所以准确说法不是“只选了 ReAct”，而是:

> 主路径为了通用性用 ReAct，复杂任务上已经引入了更接近 Plan-and-Execute / Graph Workflow 的实现。

#### 为什么主路径仍然偏 ReAct

因为 ReAct 适合这几类任务:

- 用户问题短
- 工具数不算极多
- 动作链不长
- 要求实时流式反馈
- 实现复杂度要控制

ReAct 的优点:

- 实现简单
- 交互快
- 流式体验好
- 对开放式任务适配强

#### 为什么没把所有任务都改成 Plan-and-Execute

因为 Plan-and-Execute 也有成本:

- 先规划再执行，首 token 更慢
- 规划可能过度
- 对短任务反而浪费 token
- 工程复杂度更高

#### 项目里的证据

主路径 Agent:

- [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py)
- [chat.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/chat.py)

都在用:

- `create_agent(...)`

而复杂图式任务:

- [deepsearch/stream_graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/stream_graph.py)
- [lingseek/agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/lingseek/agent.py)

已经不是纯 ReAct 了。

#### 面试推荐说法

> 不是简单地二选一。这个项目主链路偏 ReAct，因为它适合通用问答和工具调用，响应快、实现轻、流式体验好；但在 DeepSearch 和 LingSeek 这种复杂任务里，其实已经引入了任务图和反思循环，更接近 Plan-and-Execute 或 Graph-based Workflow。也就是说，我们是按任务复杂度选架构，而不是全站只用一种范式。

---

### 3.4 为什么采用多 Agent 结构？

从项目源码看，多 Agent 的动机主要有 4 个:

1. 职责隔离

不同 Agent 关注不同能力:

- 通用对话 Agent
- MCP Agent
- Skill Agent
- DeepSearch Agent
- Mars Agent
- LingSeek Agent

2. 工具和能力边界更清晰

例如:

- MCP 能力封装成 MCP Agent
- Skill 能力封装成 Skill Agent

然后再作为 tool 暴露给更上层 Agent。

3. 更适合扩展

新能力可以作为新 Agent 追加，而不是把所有逻辑都塞进一个巨型 Agent。

4. 更适合复杂任务拆分

例如 LingSeek 的任务图、DeepSearch 的研究循环，本质都是把复杂任务拆成多个子执行单元。

#### 项目里的一个关键设计

在 [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py) 里:

- MCP Agent 可以被包装成 tool
- Skill Agent 也可以被包装成 tool

这说明这里的多 Agent 不是完全平行的，而是“Agent as Tool”的分层结构。

#### 面试里可以这样说

> 采用多 Agent 结构主要是为了职责解耦和能力扩展。这个项目里一个重要设计是把 MCP Agent、Skill Agent 进一步封装成上层 Agent 可调用的工具，相当于把复杂能力模块化，而不是把所有工具、记忆、规划、检索都堆在一个 Agent 里。

---

### 3.5 多 Agent 有哪些架构范式？应用场景分别是什么？

这题适合答成“范式地图”。

#### 1. Router / Dispatcher 模式

特点:

- 先做意图分类
- 再把请求路由给最合适的 Agent

适合:

- 客服分流
- 多领域助手
- 不同能力模块明确分工

#### 2. Supervisor-Worker 模式

特点:

- 一个总控 Agent 负责任务拆分
- 多个 Worker Agent 执行子任务
- 最后汇总

适合:

- 报告生成
- 多步骤任务
- 多工具协同

#### 3. Agent as Tool 模式

特点:

- 把一个 Agent 封装成另一个 Agent 的工具

适合:

- 专家能力封装
- 技能模块复用
- 平台化扩展

这个项目就有这种味道。

#### 4. Plan-and-Execute 模式

特点:

- 先生成计划
- 再逐步执行

适合:

- 长流程任务
- 需要显式依赖关系的任务
- 对稳定性要求高的复杂任务

#### 5. Graph Workflow 模式

特点:

- 节点和边显式定义
- 可以有条件跳转、循环、并行、反思

适合:

- DeepSearch
- 多跳研究
- 审批流、工作流类问题

这个项目的 `DeepSearch`、`LingSeek` 都已经有点这个方向。

#### 6. Debate / Critic 模式

特点:

- 多个 Agent 互相辩论、审查、打分

适合:

- 高准确率问答
- 推理校验
- 风险审计

#### 7. Blackboard / Shared Memory 模式

特点:

- 多个 Agent 共享一块任务板或共享状态

适合:

- 协同写作
- 多模块协作决策

---

## 4. MCP、A2A、Skill、Function Call

### 4.1 MCP 与 A2A 是什么？

#### MCP 是什么

MCP = Model Context Protocol。

它的核心是:

- 为模型接工具、资源、prompt 提供统一协议

在这个项目里，MCP 是主线能力之一，已经有完整实现:

- 连接配置
- 多 transport
- 动态发现工具
- 包装成 LangChain Tool

相关代码在:

- [sessions.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/sessions.py)
- [multi_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/multi_client.py)
- [tools.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/load_mcp/tools.py)

#### A2A 是什么

A2A 一般指 Agent-to-Agent 协议，也就是 Agent 之间如何发现对方能力、发消息、接收流式结果。

这个项目里:

- A2A 不是主业务链路
- 但有测试样例

见:

- [test_a2a/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/client.py)
- [test_a2a/main.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/main.py)

所以面试时不要说“项目全面使用了 A2A”，更准确说法是:

> MCP 是项目主路径能力，A2A 在项目里更多还是测试和探索性样例。

---

### 4.2 它们之间传输信息的格式是什么？

#### MCP 的信息格式

MCP 的本质是结构化协议消息。

在这个项目里，MCP 工具最终被转换成:

- `name`
- `description`
- `inputSchema`

调用时走:

- `session.call_tool(tool.name, arguments)`

返回后再被转换为:

- 文本内容 `TextContent`
- 非文本内容如 `ImageContent` / `EmbeddedResource`

可以理解为“结构化 JSON schema + 协议消息”。

#### A2A 的信息格式

从 [test_a2a/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/client.py) 可以看到，它构造的消息类型包括:

- `SendStreamingMessageRequest`
- `MessageSendParams`
- `Message`
- `Role`
- `Part`
- `TextPart`

也就是说，A2A 更像:

- 一个消息对象
- 里边包含 role、message_id、parts
- `parts` 中可以放文本或其他类型片段

所以两者都不是“纯字符串传输”。

更准确地说:

- MCP 偏“工具协议和 schema 驱动”
- A2A 偏“Agent 间消息协议和多 part 消息体”

---

### 4.3 Skill 和 function call 有什么区别？

这个问题在项目里特别适合结合“Skill Agent”来讲。

#### Function Call 是什么

Function call 更偏:

- 单次调用一个明确函数
- 输入输出 schema 明确
- 一次动作就结束

例如:

- 查天气
- 发请求
- 搜索网页

#### Skill 是什么

Skill 更像:

- 一组复合能力
- 背后可能有自己的 prompt、工具集、执行逻辑
- 本质上是更高阶的能力封装

在这个项目里，Skill 并不是普通函数，而是:

- 一个 Skill Agent 被封装成上层 tool

见:

- [skill_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/skill_agent.py)
- [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py)

所以你可以这样区分:

- function call = 原子动作
- skill = 复合能力模块

#### 面试推荐说法

> Function call 更像“调用一个函数”；Skill 更像“调用一个会自己组织内部流程的小专家”。这个项目里 skill 的典型落地方式就是 Skill Agent as Tool，所以它不是单个 API，而是一个更高层的能力封装。

---

## 5. 记忆相关

### 5.1 长短期记忆怎么存储的？

这个项目没有特别严格地定义“短期记忆层”和“长期记忆层”两个完全独立模块，但可以从实现上这样理解:

#### 短期记忆

更接近:

- 当前对话 messages
- 当前会话历史
- `run_id/dialog_id` 维度下的上下文

也就是 prompt 里直接参与本轮推理的上下文。

#### 长期记忆

更接近:

- `AsyncMemory` 持久化到向量存储中的事实记忆

位置在:

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)

默认底层向量库是:

- `Chroma`

并通过 metadata 区分:

- `user_id`
- `agent_id`
- `run_id`
- `actor_id`

#### 但要强调

这个项目没有把长短期记忆显式做成一套非常成熟的双层系统，比如:

- STM buffer
- LTM store
- 定期 consolidation
- 遗忘机制

所以比较准确的表达是:

> 项目有会话上下文和持久化事实记忆，但没有把长短期记忆彻底产品化成经典双层架构。

---

## 6. 工具调用、上下文管理、通信与性能

### 6.1 关于通信，你是如何处理的？如何平衡性能与质量？

这题可以从前后端流式通信和模型/工具通信两层讲。

#### 第一层: 前后端用户交互通信

项目主链路采用的是:

- `FastAPI StreamingResponse`
- `text/event-stream`
- 前端 `fetch-event-source`

也就是 SSE 流式通信。

这么做的优点:

- 比轮询体验好
- 比 WebSocket 简单
- 对“服务端不断吐 token 给前端”的场景很适合

性能和质量的平衡点在于:

- 先尽快返回流式内容，提升感知速度
- 后端内部再异步组织工具和模型结果

#### 第二层: 模型和工具的内部通信

项目里大量使用:

- `asyncio`
- `asyncio.gather`
- `Queue`
- 流式 chunk 事件

例如:

- RAG 中 embedding 批量并发
- MCP tools 并发调用
- Mars 中 reasoning 流与 agent 流并行组织

#### 面试推荐说法

> 通信层我会区分用户侧和系统侧。用户侧为了交互体验采用 SSE 流式输出，优先保证首 token 快；系统侧则用 asyncio 并发组织 embedding、检索、工具调用和事件流。性能和质量的平衡点在于，不盲目并发所有步骤，而是把高成本步骤放到真正必要时执行，比如多阶段召回、工具调用和 reasoning 流拆通道处理。

---

### 6.2 关于工具调用和上下文管理，有什么处理方式？

这题要结合项目实际，既讲已有方案，也讲痛点。

#### 项目里已经考虑到的点

在 [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py) 里，作者明显意识到了“工具太多会撑爆上下文”的问题。

可以看到:

- `MAX_TOOLS_SIZE = 10`
- 设计了 `search_available_tools(...)`

这个工具的思路是:

1. 工具过多时先不把全部工具直接绑给模型
2. 先给一个“工具搜索器”
3. 让模型先搜索相关工具
4. 再把相关工具放进 `available_tools`

而且是通过:

- `Command(update={"available_tools": found_tools, "messages": [tool_msg]})`

动态更新 agent state

这个设计本身非常漂亮，因为它本质上是在做:

- 工具检索
- 工具上下文压缩
- 动态工具暴露

#### 但也要诚实说明

当前这套机制在主路径里并没有完全启用。

因为 `setup_react_agent()` 里实际仍然是:

- `tools=self.tools + self.mcp_agent_as_tools + self.skill_agent_as_tools`

而注释掉的才是更激进的按 `search_tool` 先检索再暴露。

所以准确说法是:

> 项目已经有动态工具裁剪的设计思路，但目前主链路仍偏直接绑定工具，说明这部分意识到了问题，但还没完全产品化。

#### 如果面试官问痛点

可以直接说:

- 工具太多，模型会选不准
- 描述太长，上下文 token 激增
- 工具太少，任务覆盖不足
- 同类工具过多，模型容易混淆

#### 我的优化建议

1. 工具分层

- 高频核心工具常驻
- 长尾工具走检索式暴露

2. 工具路由

- 先意图分类，再缩小候选工具集

3. 工具描述压缩

- 只保留模型判别所需的关键词，不把冗长说明全塞进去

4. 工具使用反馈闭环

- 统计命中率、误用率、调用成功率

---

### 6.3 关于容灾，你是如何解决的？

这题是综合题，回答时最好分层。

#### 先说项目里已经看到的容灾思路

1. 状态可追踪

知识库文件上传后有解析状态:

- `process`
- `success`
- `fail`

见 [knowledge_file.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/knowledge_file.py)

这属于最基础但非常重要的任务状态容灾。

2. 工具调用异常兜底

在多个 Agent middleware 里，工具调用异常会被 catch，并转成可返回的 `ToolMessage` 或错误事件，而不是直接把整个 Agent 打崩。

3. 超时与取消

部分场景下对 agent task 做了 `wait_for` 和 `cancel`。

4. 会话层参数校验

MCP `create_session(...)` 会严格校验 transport 必要字段，不合法配置直接 fail fast。

5. 懒加载和按需连接

Milvus collection 懒加载、MCP session 按需创建，都是一种降低长期资源占用和异常扩散面的方式。

#### 但要诚实说，这个项目还没看到特别完整的容灾体系

比如没明显看到完善的:

- 熔断器
- 重试退避策略
- 死信队列
- 降级路由
- 多副本切换
- 全链路告警

所以面试最好答成:

> 现阶段项目里已经做了任务状态、异常兜底、部分超时取消和 fail-fast 校验，但如果从完整容灾体系看，还需要继续补重试、熔断、降级、监控和回放机制。

#### 我会怎么补

1. 模型层

- 超时
- 重试
- 主备模型切换

2. 工具层

- 调用超时
- 熔断
- fallback tool

3. 检索层

- Milvus 不可用时回退 ES
- summary 检索不足时回退 content

4. 任务层

- 长任务状态持久化
- 支持断点恢复

5. 监控层

- token 消耗
- 调用成功率
- 检索命中率
- 工具错误率

---

## 7. 高频追问的推荐话术

### 7.1 如果面试官问: 你们 ReAct 的问题你自己也承认了，那为什么还敢用？

你可以回答:

> 因为架构不是非黑即白的。短任务、轻工具场景下 ReAct 的工程性价比很高，响应快、实现轻；复杂任务我们已经在 DeepSearch 和 LingSeek 里引入了图式工作流。所以不是盲目坚持 ReAct，而是按任务复杂度分层选型。

### 7.2 如果面试官问: 你们的记忆系统算成熟吗？

你可以回答:

> 我会说它已经具备“持久化事实记忆”的核心能力，但还不算完整的长期记忆体系。优势是已经做了 facts 抽取和 ADD/UPDATE/DELETE，而不是聊天记录直接堆库；不足是还没做完整的记忆分层、遗忘和重要性管理。

### 7.3 如果面试官问: 你们 RAG 的亮点到底是什么？

你可以回答:

> 亮点不在某个单点库，而在整条链路比较完整。包括 PDF 先转 Markdown 保结构、基于标题层级切块、摘要向量和正文向量双路召回、ES+Milvus 混合检索、chunk 去重以及 rerank 重排。这些细节共同决定了检索质量。

---

## 8. 最后给你的总复述

如果这批题要压缩成一段总回答，我建议你这样说:

> 这个项目在 RAG、Agent、MCP 和记忆上都做了比较工程化的设计。RAG 不是简单 split text，而是先按文件类型适配，PDF 转 Markdown 后按标题层级切 chunk，并用正文向量、摘要向量、混合检索和 rerank 提升召回质量；评估方面项目里已经有基于 RAGAS 的离线脚本，但还没形成完整持续评测体系。Agent 这边主链路偏 ReAct，因为响应快、实现轻，但在 DeepSearch 和 LingSeek 上已经用了图式工作流和任务图，不是全站只靠 ReAct。MCP 是项目主线能力，支持多 transport、动态发现远程工具并包装成 LangChain Tool；A2A 在仓库里更多是测试样例。记忆方面已经有持久化事实记忆，但还不算完整的长期记忆体系。工具调用和上下文管理方面，项目已经意识到工具过多会撑爆上下文，也设计了动态工具搜索和暴露机制，只是目前还没有完全产品化。容灾方面已有状态追踪、异常兜底和部分超时取消，但完整的重试、熔断和降级体系仍然是后续优化方向。 

