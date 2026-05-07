# 项目面试题详解: RAG、Agent、MCP、记忆与容灾（扩写版）

## 1. 说明

这份文档是在上一版问答的基础上做的“可背诵扩写版”。

目标不是只给你一个简短提纲，而是尽量把每道题扩成你在面试里能直接说出口的答案。回答方式遵循三个原则：

1. 能结合项目源码的，尽量结合到具体模块、类、方法和数据流
2. 项目里没有明确落地的，不会硬说做过，会明确区分“项目现状”和“如果继续做我会怎么设计”
3. 不贴大段完整代码，但尽量讲清代码层面的关键实现细节

你可以把这份文档理解成“带项目证据的标准答案库”。

---

## 2. RAG 相关

### 2.1 RAG 中 chunk 怎么分的？

如果面试官问这个问题，我建议你先给结论，再讲细节。

#### 可以直接说的结论

这个项目的 chunk 不是简单按固定长度一刀切，而是“先保留文档结构，再做长度控制”的切分策略。核心做法是：

- 不同文件类型先走不同解析器
- PDF 先转 Markdown
- Markdown 再按标题层级切块
- 每个 chunk 不只包含正文，还会带上标题路径 `header_path`
- 长段落会做安全切分，避免切坏链接、图片语法和句子边界
- chunk 之间保留 overlap，减少边界信息丢失

#### 代码证据

相关代码主要在：

- [parser.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/parser.py)
- [markdown.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/markdown.py)
- [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py)

入口是 `DocParser.parse_doc_into_chunks(...)`。它不是直接读取文本后 `split(500)`，而是先按文件后缀路由：

- `md` -> `markdown_parser`
- `txt` -> `text_parser`
- `docx` -> `docx_parser`
- `pdf` -> `pdf_parser`
- `pptx` -> `pptx_parser`
- 图片 -> 先 OCR / 转文本
- Excel -> 先转文本
- 其他文本类格式 -> 先转 txt

也就是说，系统先做“格式归一化”，再做 chunk。

#### PDF 为什么要先转 Markdown

项目在 [pdf.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/doc_parser/pdf.py) 中用 `pymupdf4llm.to_markdown(...)` 将 PDF 转成 Markdown，并且：

- `write_images=True` 导出图片
- 把图片上传到 OSS
- 重写 Markdown 中的图片链接
- 再把 Markdown 交给 Markdown parser 做结构化切块

这背后的思路是：PDF 的难点不是“提取字符”，而是“保留结构”。如果你直接抽纯文本，标题层级、图片上下文、段落边界很容易丢；先转 Markdown，可以把文档的结构骨架尽量保留下来，后面的 chunk 才更有语义。

#### Markdown chunk 是怎么切的

真正的切块逻辑在 `MarkdownParser`：

- `min_chunk_size = 256`
- `max_chunk_size = 512`
- `overlap_size = 128`

它会做几件很关键的事：

1. 解析标题层级

通过正则 `^(#{1,5})\\s+(.+)$` 识别 Markdown 标题，维护 `current_headers`，再拼出一个标题路径，例如：

`系统设计 > 缓存模块 > 一致性方案`

2. 把 `header_path` 拼进 chunk 内容

也就是说，chunk 不是只有正文，还会包含章节上下文。这样做的好处是，向量检索时，embedding 看到的不只是局部段落，还能同时感知它属于哪一章、哪一节，召回更稳定。

3. 长段落不是机械硬切

`find_link_boundaries(...)`、`is_safe_cut_position(...)`、`find_best_cut_position(...)` 这些方法说明作者在刻意避免：

- 把 Markdown 链接从中间切断
- 把图片语法从中间切断
- 把句子从很奇怪的位置截断

4. 有 overlap

`overlap_size=128` 意味着相邻 chunk 会有重叠区域，这样可以降低一种典型问题：关键信息刚好落在 chunk 边界，导致检索时两边都不完整。

#### 为什么这比定长切分更合理

因为 RAG 里 chunk 的质量会直接影响后面的三件事：

1. Embedding 是否稳定
2. 检索召回是否准确
3. 拼给模型的上下文是否完整

如果简单定长切分，常见问题是：

- 一个定义和它的解释被切开
- 标题和正文被拆散
- 列表项只切到一半
- 表格说明被砍断
- 链接、代码块、图片描述残缺

而这个项目的 chunk 逻辑明显是在尽量避免这些问题。

#### 进一步可优化的方向

如果面试官追问“这套 chunk 还有什么可以优化”，你可以补：

- 可以给 chunk 增加更显式的 metadata，例如页码、标题路径单独字段、文档章节编号
- 可以按文档类型动态调整 chunk size，而不是所有格式都用同一套阈值
- 对表格、代码块、FAQ 等结构化片段，可以做专门的 chunk 策略
- 可以做父子 chunk，比如父 chunk 保全局语义，子 chunk 保局部检索精度

#### 适合背诵的回答

> 这个项目的 chunk 不是简单定长切分，而是“结构优先”的策略。入口在 `DocParser.parse_doc_into_chunks`，会先按文件类型分流，PDF 先通过 `pymupdf4llm` 转 Markdown，再交给 Markdown parser。Markdown chunk 阶段会解析标题层级，维护 `header_path`，把标题路径和正文一起作为 chunk 内容，同时设置 `min_chunk_size=256`、`max_chunk_size=512`、`overlap_size=128`。对于超长段落，代码里还会通过 `find_best_cut_position` 之类的方法避开链接、图片和句子边界。所以它的核心思想不是“切得均匀”，而是“尽量保留语义结构”，这对后续 embedding 和召回质量影响非常大。 

### 2.2 用的什么 embedding 模型？

#### 直接回答

这个项目默认的 embedding 模型是配置在 `config.yaml` 里的 `text-embedding-v4`，通过 OpenAI-compatible 接口调用。

#### 代码证据

配置位置：

- [config.yaml](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/config.yaml)

对应字段：

- `multi_models.embedding.model_name`
- `multi_models.embedding.base_url`
- `multi_models.embedding.api_key`

RAG 侧的 embedding 实现位于：

- [embedding.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/embedding.py)

记忆侧的 embedding 入口则通过：

- [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/models/manager.py)
- [embedding.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/models/embedding.py)

也就是说，这个项目把 embedding 能力统一封装成了模型管理的一部分，而不是在业务代码里到处散落调用。

#### RAG 侧 embedding 是怎么调的

`services/rag/embedding.py` 里的 `get_embedding(...)` 有几个值得提的点：

1. 使用 `AsyncOpenAI(...).embeddings.create(...)`

说明接口是兼容 OpenAI 协议的，不和具体厂商 SDK 深度耦合。

2. 小批量和大批量采用不同策略

- 如果输入是一条字符串，或者列表长度不超过 10，直接一次请求
- 如果超过 10 条，就分 batch
- 通过 `asyncio.Semaphore(5)` 控制并发批次数

3. 返回格式统一

- 单条 query 返回一个向量
- 多条 query 返回向量列表

#### 这个实现背后的工程考量

embedding 在 AI 项目里看起来只是“调个接口”，但真正上线时要考虑：

- QPS
- 吞吐
- 接口限流
- 成本
- 批量化效率

这个项目虽然实现不算特别复杂，但已经做了两个很实用的工程点：

- batch
- 并发限制

这就比“每段文本单独打一遍接口”成熟一些。

#### 还能怎么优化

如果面试官追问“embedding 还能怎么优化”，可以说：

- 做 embedding 缓存，避免重复向量化
- 对超长文本先做规范化或摘要后再嵌入
- 按文本长度动态批处理，减少单次 payload 波动
- 将热点 chunk 和高频 query 的 embedding 做持久化缓存
- 对不同场景区分 embedding 模型，比如知识库和记忆库不一定用同一个模型

#### 适合背诵的回答

> 项目默认配置的 embedding 模型是 `text-embedding-v4`，通过 OpenAI-compatible 接口来调，代码在 `services/rag/embedding.py`。这里不是简单一条条去请求，而是做了 batch 和并发控制：小于等于 10 条就一次性请求，超过 10 条就分批，并通过 `Semaphore(5)` 限制并发。这种实现说明我们不仅关心“能不能生成向量”，也考虑了吞吐、限流和成本。对我来说，embedding 模型本质上不是一个孤立组件，而是检索链路的基础设施，所以要统一管理和稳定调用。 

### 2.3 召回策略是什么？

#### 直接结论

这个项目的召回策略不是单一的向量 top-k，而是多阶段混合召回。完整链路是：

1. Query Rewrite
2. Summary / Content 双路向量召回
3. 可选的 ES + Milvus 混合检索
4. 按 `chunk_id` 去重
5. Rerank 重排
6. 分数阈值过滤
7. 拼接上下文返回给模型

#### 代码证据

主要看：

- [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py)
- [retrieval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/retrieval.py)
- [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py)
- [es_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/es_client.py)
- [rerank.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/rerank.py)

#### 第一层：Query Rewrite

`RagHandler.query_rewrite(...)` 会先把用户 query 重写成多个 query。

它解决的不是“检索速度”，而是“召回覆盖率”。很多时候用户问题和文档原文不是一种表述方式，比如：

- 用户问的是口语化说法
- 文档里是正式术语
- 用户问题过短，语义不完整

把 query rewrite 成多个近义或扩展 query，可以提高召回的 recall。

#### 第二层：Summary / Content 双路召回

Milvus collection 里同时存了两个向量字段：

- `embedding`：正文向量
- `embedding_summary`：摘要向量

对应方法：

- `search(...)`
- `search_summary(...)`

这很关键，说明项目不是只对原文做 embedding，还对 chunk 摘要做了第二套 embedding。摘要向量通常更聚焦，适合先做语义概括层面的召回；正文向量更细节，适合兜底和精确补充。

`rag_query_summary(...)` 的逻辑是：

- 先按 summary 召回
- 如果结果数量不足 `top_k`
- 再回退到 content 召回

这个设计其实就是在平衡：

- 摘要召回的聚焦性
- 正文召回的完整性

#### 第三层：混合检索

如果配置里打开 `enable_elasticsearch`，项目会同时做：

- ES 关键词检索
- Milvus 语义向量检索

这就是典型 hybrid retrieval。

为什么要 hybrid？因为纯向量检索和纯关键词检索各有短板：

- 纯向量检索容易错过某些必须精确命中的术语
- 纯关键词检索对近义表达、语义泛化能力弱

混合后可以兼顾：

- 术语精确匹配
- 语义相似匹配

#### 第四层：去重

项目在 `mix_retrival_documents(...)` 里通过 `seen_chunk_ids` 按 `chunk_id` 去重。

这是一个很重要但很容易被忽略的工程细节。因为：

- 同一个 chunk 可能被多个 rewrite query 召回
- 同一个 chunk 可能同时被 ES 和 Milvus 命中

如果不去重，后面 Rerank 和最终拼接上下文都会被重复内容污染。

#### 第五层：Rerank

召回之后，项目还会调用独立的 rerank 模型重排。

这个阶段的职责一定要讲清楚：

- 检索阶段负责“找回来”
- Rerank 阶段负责“排得准”

很多人面试时只会说“我用了向量检索”，但实际 RAG 效果很大一部分取决于 Rerank。

#### 第六层：阈值过滤和上下文拼接

Rerank 后不是无脑取前 K，还会根据：

- `min_score`
- `top_k`

进行过滤，再把最终相关内容拼接成字符串上下文。

#### 这套策略的优点

1. Recall 更高

因为有 rewrite 和 hybrid

2. Precision 更高

因为有 summary/content 双路和 rerank

3. 更稳

因为有 fallback，不是单点失败

#### 这套策略的潜在问题

也要敢于说问题：

- 查询链路更长，时延更高
- 组件多了以后调参复杂
- ES 和 Milvus 分数空间不一致，结果融合如果太粗糙会有误差
- Query Rewrite 如果质量不稳定，也会带来噪声召回

#### 适合背诵的回答

> 这个项目的召回不是简单的向量 top-k，而是一个多阶段混合召回链路。首先会做 Query Rewrite，提高召回覆盖率；然后在 Milvus 里同时支持正文向量和摘要向量两条检索路径，优先按 summary 召回，不足时回退到 content；如果开启 Elasticsearch，还会做 ES + Milvus 的 hybrid retrieval；之后再按 `chunk_id` 去重，防止重复片段污染结果；最后使用独立的 rerank 模型重排，并结合 `top_k` 和 `min_score` 做过滤。它的核心思想是把召回和排序拆开处理，用多阶段策略平衡 recall 和 precision。 

### 2.4 怎么评估检索的准确率？

#### 回答思路

这个问题不要只说一个指标，而要分成两层：

1. 检索层评估
2. 端到端 RAG 评估

#### 第一层：只评检索

如果单独评估 retrieval，不看最终生成回答，常见指标包括：

- Recall@K
- Precision@K
- Hit Rate
- MRR
- nDCG

这些指标分别回答不同问题：

- `Recall@K`：正确 chunk 有没有被召回到前 K 个结果里
- `Precision@K`：前 K 个召回结果里，有多少真正相关
- `Hit Rate`：是否至少命中一个相关 chunk
- `MRR`：第一个正确 chunk 排得有多靠前
- `nDCG`：如果相关性不是二值而是多等级，能更合理地反映排序质量

如果是知识库问答项目，我会特别重视：

- Recall@K
- MRR

因为对 RAG 来说，最常见的问题不是“完全搜不到”，而是“搜到了但排得太后面”，导致拼给模型的上下文不够好。

#### 第二层：评估整个 RAG 回答

如果不仅评检索，还评最终回答质量，就要看：

- Context Precision
- Context Recall
- Faithfulness
- Answer Relevancy

这里你要能解释含义：

- `Context Precision`：给模型的上下文里有多少是真的相关
- `Context Recall`：该召回到的上下文是不是大多都召回到了
- `Faithfulness`：回答是否忠于提供的上下文，有没有胡编
- `Answer Relevancy`：回答是不是针对用户问题，不是偏题的废话

#### 项目里有没有评估实现

这个项目里是有评估脚本的，在：

- [eval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/eval.py)

这个脚本使用：

- `ragas.evaluate(...)`

指标就是：

- `context_precision`
- `context_recall`
- `faithfulness`
- `answer_relevancy`

它会：

1. 构造测试问题
2. 获取 retriever 返回的 context
3. 生成 answer
4. 配上 ground truth
5. 跑 RAGAS
6. 最终导出到 Excel

#### 真正落地时我会怎么做

如果面试官追问“只靠 RAGAS 够吗”，你可以答：

不够。RAGAS 更像是一个很好的起点，但完整评估体系至少要有：

1. 固定 benchmark 数据集
2. 版本化评测
3. 每次改 chunk / rewrite / rerank 策略都跑回归
4. 检索层和生成层分开打分
5. 线上加入用户反馈闭环

#### 适合背诵的回答

> 评估检索准确率我会分两层来看。第一层是 retrieval 本身，常用 Recall@K、Precision@K、MRR、nDCG 这些指标，重点看正确 chunk 能否被召回，以及排位是否足够靠前。第二层是端到端 RAG 评估，要结合 Context Precision、Context Recall、Faithfulness、Answer Relevancy 这些指标，因为真正影响用户体验的不只是“有没有召回”，还包括“给模型的上下文是不是干净”和“回答是不是忠于上下文”。这个项目里已经有 `services/rag/eval.py` 的 RAGAS 脚本，说明我们至少做过离线评估思路的验证。 

### 2.5 有没有做过这方面的评估？

#### 实事求是的说法

有做过，但从源码落地程度看，更像是“离线评估脚本和方法验证”，还不是完整的生产级持续评估平台。

#### 为什么这么说

因为项目里确实有：

- [eval.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/eval.py)

它会：

- 读 `test.csv`
- 构造 `questions / ground_truths / contexts / answers`
- 调用 `ragas.evaluate`
- 输出 Excel

这说明团队已经有评估意识，知道不能只凭主观感觉判断 RAG 好坏。

但是从仓库结构和业务流程看，目前没有明显看到：

- 系统化 benchmark 数据集管理
- 评估任务自动化流水线
- 每次策略变更后的回归评测
- 线上日志自动抽样评估
- 召回层单独标注集

所以不能夸成“我们已经有完备的评测平台”，这会显得不实在。

#### 面试里最好的说法

> 这方面项目里已经有离线评估脚本，说明不是完全拍脑袋做 RAG。我们至少做过 RAGAS 这一类基于上下文和回答质量的评估验证。但从成熟度看，它还属于离线实验和方法验证阶段，不算完整的生产级持续评估体系。如果继续往下做，我会补固定测试集、版本化评测、回归评估和线上反馈闭环。 

#### 如果面试官追问“为什么很多团队评估做不起来”

你可以加一句：

因为真正难的不是跑一个评估脚本，而是：

- 构造稳定的数据集
- 定义什么叫“正确”
- 区分检索问题和生成问题
- 把评测接入持续迭代流程

这句话会显得你更懂工程落地。

### 2.6 关于 RAG 检索前戏：你是如何处理数据的？一刀切？JSON？还是 Markdown？

#### 直接结论

这个项目的数据预处理思路不是一刀切，而是“异构文档先结构化，再统一进入 chunk 流程”。项目整体更偏向把多种格式最终归一成：

- 结构化 Markdown
- 或可解析文本

再进入分块、摘要、向量化和索引流程。

#### 为什么这题很重要

很多面试官问“RAG 前戏”，其实是在看你有没有意识到：RAG 的效果很大程度上取决于数据处理，而不只是检索器或模型。

如果预处理差，后面全都救不回来。

#### 这个项目具体怎么做

1. PDF

优先转 Markdown，并保留图片和结构

2. DOCX

走 docx parser，最终也倾向于进入更结构化的解析路径

3. Markdown

直接按标题层级解析

4. TXT / HTML / CSV / JSON

转成文本类再走 text parser

5. Excel

转 txt 再处理

6. 图片

OCR 或转文本后进入统一切块流程

#### 它不是在做什么

它不是：

- 所有文件先抽纯文本
- 再统一 `split(500)`

这种简单做法最大的问题是丢结构。

#### 为什么更偏 Markdown

因为 Markdown 是一个很好的中间态：

- 结构轻
- 标题层级清晰
- 段落、列表、图片语法都能表达
- 比 PDF 原始格式更容易做程序化解析

所以项目里 PDF 先转 Markdown，再按 Markdown 结构切块，本质上是在选择一种“既保留结构又便于处理”的中间表示。

#### 如果面试官问“JSON 适不适合做中间格式”

你可以说：

适合，但要看场景。

- 如果原始数据本来就是结构化知识，比如 FAQ、产品规格、表格记录，JSON 很适合
- 如果原始数据是文档，尤其是 PDF、说明书、手册，Markdown 往往更自然

这个项目显然更偏“文档型知识库”，所以 Markdown 是更合理的中间态。

#### 适合背诵的回答

> 这个项目的预处理不是一刀切，而是先按文件类型做适配，再尽量归一到结构化 Markdown 或可解析文本。比如 PDF 先转 Markdown 保留标题和图片上下文，Markdown 再按标题层级切块；Excel、图片、其他文本类格式则会先转成统一文本再处理。这样做的原因是 RAG 的瓶颈很多时候不在检索器，而在原始数据有没有被正确结构化。如果一上来就抽纯文本再固定长度切块，标题、段落、列表和图文关系都会被破坏，后面的检索质量自然上不去。 

### 2.7 RAG，为什么选 Chroma 而不是 Qdrant 或者 Milvus？

#### 先纠正一个事实

如果面试官这么问，你要先非常冷静地纠正：

这个项目的知识库 RAG 主链路并没有选 Chroma，而是选了 Milvus。

#### 项目中的真实情况

知识库 RAG 侧：

- 用的是 `Milvus`

位置：

- [knowledge_file.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/knowledge_file.py)
- [rag_handler.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag_handler.py)
- [milvus_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/rag/vector_db/milvus_client.py)

记忆系统侧：

- 默认用的是 `Chroma`

位置：

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)
- [vector_stores/__init__.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/vector_stores/__init__.py)

所以更准确的说法应该是：

> 知识库主路径用 Milvus，记忆系统默认用 Chroma，两者按场景分开选型。

#### 为什么知识库更适合 Milvus

从这个项目的实现风格看，选择 Milvus 是合理的，原因主要有：

1. 更偏文档级、知识库级的向量检索

知识库通常：

- 数据量更大
- 检索请求更集中
- 需要独立 collection 管理

这个项目里甚至是“每个 knowledge_id 一个 collection”，这跟 Milvus 的使用方式很契合。

2. 更明确的 ANN 索引控制

项目里显式设置了：

- `IVF_FLAT`
- `L2`
- `nlist`
- `nprobe`

说明作者有在按向量库思维进行检索参数控制。

3. 适合后续扩容和独立运维

对知识库来说，Milvus 这类专业向量数据库通常比轻量内嵌向量库更合适。

#### 为什么记忆默认用 Chroma

因为记忆系统的特点不太一样：

- 数据规模通常更小
- 更偏用户级 / 会话级
- 读写更频繁
- 更强调开发和接入轻量性

Chroma 的优势在于：

- 接入轻
- 本地化方便
- 对中小规模事实记忆很够用

所以这里不是“谁更高级”，而是按场景选型。

#### Qdrant 怎么看

如果面试官追问“为什么不是 Qdrant”，可以说：

Qdrant 也是很优秀的选择，尤其在：

- 向量 + payload filter
- 检索 API 易用性
- 工程接入体验

方面都不错。

但这个项目当前没有实际落地 Qdrant，从代码看也没有统一抽象到可随时热切换多个向量库实现的程度，所以不能说“评估后故意没选”，更准确说法是：当前项目实际落地的是 Milvus + Chroma 组合。

#### 适合背诵的回答

> 这题在这个项目里要先纠正一下：知识库 RAG 主路径其实用的是 Milvus，不是 Chroma；Chroma 默认用在记忆系统里。原因是两者场景不同。知识库是文档级、大规模检索，更适合 Milvus 这种专业向量库，项目里也确实按 `knowledge_id` 建 collection，并显式配置了 IVF_FLAT、nlist、nprobe 这些参数；而记忆更偏用户级、小规模、高频读写场景，用 Chroma 接入更轻、更方便。Qdrant 当然也是很好的选择，但这个项目当前并没有实际落地 Qdrant。 

### 2.8 不上 GraphRAG 的原因是什么？或者说传统 RAG 混合检索的局限是什么？

#### 项目现状先说清楚

这个项目目前没有真正落地 GraphRAG。

从代码可以看到，在记忆模块里虽然预留了 graph 相关结构，但默认是：

- `self.enable_graph = False`
- `self.graph = None`

位置在：

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)

这说明团队至少意识到图式能力的方向，但当前主路径仍然是传统 chunk-based RAG + hybrid retrieval。

#### 为什么很多项目不上 GraphRAG

如果你面试时只说“太复杂”，会显得浅。更好的答法是拆成 4 个层次：

1. 建图成本高

GraphRAG 一般至少要做：

- 实体抽取
- 关系抽取
- 图存储
- 图检索
- 路径推理

这条链路比传统 RAG 的复杂度高很多，不只是多接一个库。

2. 图谱质量依赖抽取质量

GraphRAG 不是“上了图就更准”，而是：

- 抽得准，图才有价值
- 抽错了，错误会被结构化放大

比如实体合并错、关系方向错、时间关系错，后面推理结果就会系统性偏掉。

3. 很多文档场景不一定需要图

如果知识库更多是：

- 产品手册
- API 文档
- 使用说明
- FAQ

那传统 chunk + hybrid retrieval 往往已经够用。

GraphRAG 更适合：

- 实体关系密集
- 多跳推理
- 跨文档关联强
- 对“谁和谁是什么关系”要求高

的场景。

4. 维护成本更高

文档更新时：

- 传统 RAG 重新切块、重新索引相对直接
- GraphRAG 还要考虑实体和边的增量更新、一致性、去重和冲突合并

#### 传统 RAG 混合检索的局限

这个问题也要敢于讲。

传统 RAG 的强项是：

- 快速找到相关片段
- 适合局部问答
- 工程实现成熟

但它的局限也很明显：

1. 对跨 chunk 的全局关系建模弱

2. 对多跳推理支持弱

如果答案需要拼多个文档、多段关系链，传统 RAG 往往比较吃力。

3. 对实体网络表达不自然

例如“这个公司和那家公司之间的投资、控制、供应链关系是什么”，图结构天然更合适。

4. 上下文拼接容易冗余

即使召回到了多个相关 chunk，也未必能在 prompt 中形成一个清晰的关系结构。

#### 项目为什么暂时不需要 GraphRAG

如果结合这个项目，我会这么解释：

当前项目的主场景更偏：

- 文档检索
- 知识问答
- 说明性内容召回

因此 chunk-based RAG + hybrid retrieval + rerank 已经能覆盖大部分需求。GraphRAG 的收益目前可能还不足以抵消额外的工程复杂度。

#### 适合背诵的回答

> 这个项目目前没有真正上 GraphRAG，主路径还是传统的 chunk-based RAG 加混合检索。原因不是简单一句“没做”，而是从工程上看 GraphRAG 成本很高，需要实体抽取、关系抽取、图存储和图检索，而且非常依赖抽取质量；从场景上看，这个项目当前更偏文档检索和说明性问答，传统 RAG 已经能覆盖大多数需求。GraphRAG 更适合那种跨文档、多跳、强关系推理的场景。传统 RAG 的局限在于它更擅长召回局部片段，但对全局关系链和复杂实体网络的表达不如图结构自然。 

## 3. Agent 架构相关

### 3.1 ReAct 进入死循环怎么办？

#### 先讲原则

ReAct 死循环本质上是一个“自主代理缺乏边界控制”的问题。常见表现有：

- 同一个工具反复调用
- 工具返回无效结果后模型继续试探
- observation 没有新信息，但 Agent 还在自我循环
- 多轮 think-act-observe 没有收敛条件

所以这个问题不能只答“加 timeout”，要从多个层面回答。

#### 项目里已经有的控制手段

这个项目确实主要采用 ReAct 风格，但也不是完全没有防护。

1. `ToolCallLimitMiddleware(thread_limit=1)`

在：

- [mars_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mars/mars_agent.py)
- [wechat_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/workspace/wechat_agent.py)

都能看到这个中间件。

它不能彻底防死循环，但至少能防止工具执行线程无限扩散，属于并发层面的约束。

2. DeepSearch 有显式 loop count

在：

- [deepsearch/graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/graph.py)
- [deepsearch/stream_graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/stream_graph.py)

都有：

- `research_loop_count`
- `max_research_loops`

这说明复杂任务流里已经有“循环上限”意识。

3. 部分场景有 `wait_for + cancel`

例如 [wechat_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/workspace/wechat_agent.py) 中对任务做了超时等待和取消。

这虽然偏粗粒度，但至少说明项目考虑过“代理不要一直挂着不结束”。

#### 项目里还缺什么

这一点要坦诚。普通 ReAct 主路径里，还没有看到特别完整的：

- 最大 step 次数控制
- 同一工具同一参数的重复调用抑制
- 连续无增益 observation 终止
- 工具失败后的明确 fallback 策略
- 模型侧 stop condition 统计

也就是说，现有防护是“有一些”，但还不算体系化。

#### 如果我来设计，会怎么防

这是面试中最加分的部分。你可以答成 5 层控制：

1. Step 上限

每个 agent run 设定最大 step 数，例如 6 到 10 步，超过直接中止并输出部分结果或降级回答。

2. 重复调用检测

记录：

- tool_name
- args hash
- observation hash

如果连续几轮出现相同调用或相同 observation，就判定为无效循环。

3. 信息增益判断

如果最近两三轮工具返回没有提供新信息，就强制停止，而不是继续让模型试探。

4. 超时和取消

对：

- 模型调用
- 工具调用
- 整个 run

都设超时，并在超时后触发 fallback。

5. 复杂任务转 graph / plan

对长任务、研究型任务，不要让纯 ReAct 自由发挥，而是切到：

- plan-and-execute
- graph workflow
- reflection loop

这其实也是项目里 DeepSearch 在做的事情。

#### 适合背诵的回答

> ReAct 死循环本质上是代理自主性过强、边界控制不足的问题。这个项目里已经有一些防护，比如 `ToolCallLimitMiddleware(thread_limit=1)` 限制工具执行线程，DeepSearch 里有 `research_loop_count` 和 `max_research_loops` 做循环上限，部分场景也用了 `wait_for + cancel` 做超时中断。但如果从完整治理角度看，还应该再补 5 类机制：第一，限制最大 agent step；第二，检测同一工具同一参数的重复调用；第三，检测连续 observation 没有信息增益时强制收敛；第四，对模型、工具和整条 run 都加超时与 fallback；第五，把长任务切到 graph 或 plan-and-execute，而不是让纯 ReAct 无限试探。 

### 3.2 为什么没考虑做长期记忆呢？

#### 先纠正一个误区

这个项目不是完全没有长期记忆，而是“已经有持久化记忆能力，但还没有做成非常成熟的长期记忆体系”。

#### 项目里已有的记忆能力

核心在：

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)

`AsyncMemory` 里已经有：

- 持久化存储
- 向量检索
- metadata 过滤
- 记忆增删改
- 记忆历史

它不是把聊天记录原样塞进去，而是会：

1. 先解析消息
2. 用 LLM 抽取 facts
3. 检索已有相似记忆
4. 再让模型判断对这条记忆是：
   - `ADD`
   - `UPDATE`
   - `DELETE`
   - `NONE`

这其实已经比很多“伪长期记忆”项目成熟了很多，因为它至少意识到了：

长期记忆最大的难点不是存，而是更新。

#### 为什么还不能说它是完整长期记忆系统

因为真正成熟的长期记忆体系通常还会有：

- 长短期分层
- 记忆重要性评分
- 遗忘机制或衰减
- 记忆 consolidation，总结与压缩
- 画像级 schema
- 记忆冲突消解策略
- 不同类型记忆分桶，例如 preference / profile / episodic / procedural

而这个项目目前更偏“事实记忆 + 向量存取”，不是完整的 LTM 体系。

#### 为什么很多团队不会一开始就做很重的长期记忆

你可以答这几点：

1. 长期记忆很容易脏

用户偏好会变，旧信息会过期，不做治理会越存越乱。

2. 价值密度低

不是所有消息都值得长期保存。大量闲聊内容其实没必要进入长期记忆。

3. 维护成本高

要做去噪、合并、更新、遗忘、召回优先级，非常耗工程资源。

4. 很多场景短期上下文 + RAG 就够了

如果项目重点是知识问答、工具调用、工作流执行，不一定需要很重的人格型长期记忆。

#### 如果继续做，我会怎么设计

1. 短期记忆

- 当前对话窗口
- 当前 run / dialog 的上下文

2. 中期记忆

- 最近几次会话的摘要
- 任务状态

3. 长期记忆

- 用户偏好
- 稳定事实
- 工具使用习惯
- procedural memory

4. 记忆治理

- 重要性评分
- 更新时间戳
- 置信度
- TTL / decay

#### 适合背诵的回答

> 这个项目其实不是完全没有长期记忆，`AsyncMemory` 已经具备持久化事实记忆能力，而且不是简单追加聊天记录，而是先抽 facts，再结合历史记忆判断是 ADD、UPDATE 还是 DELETE，这比很多项目成熟。但它还不能算完整的长期记忆体系，因为还缺少长短期分层、重要性评分、遗忘机制、画像化 schema 和 consolidation 等能力。之所以没有一开始就做得很重，是因为长期记忆最难的不是“存”，而是“存什么、怎么更新、什么时候删、如何避免脏记忆污染推理”。 

### 3.3 为什么用 ReAct 模式，不用 Plan-and-Execute 及其他 Agent 架构？

#### 先给一个成熟的回答框架

这个问题千万不要答成“ReAct 更简单所以就用了”，那样会显得你只会一种范式。更好的说法是：

> 不是简单二选一，而是按任务复杂度分层选架构。这个项目主链路偏 ReAct，因为它适合高频、短流程、工具调用型任务；但在复杂任务上，项目其实已经引入了图式工作流和任务图分解，更接近 Plan-and-Execute 或 Graph-based Workflow。

#### 为什么主链路用 ReAct

项目主链路里的 Agent，例如：

- [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py)
- [chat.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/chat.py)

都使用了：

- `create_agent(...)`

整体风格就是经典 ReAct：

- 模型思考
- 决定是否调用工具
- 工具返回 observation
- 再继续生成

这种模式适合：

1. 用户问题偏短
2. 工具调用链不会太长
3. 希望响应快、流式体验好
4. 工程实现成本要控制

ReAct 的优势在于：

- 实现轻
- 响应快
- 易于流式输出
- 对开放任务很灵活

#### 为什么不是所有地方都用 ReAct

因为纯 ReAct 的短板也很明显：

- 容易试探式乱走
- 对长任务不稳定
- 对显式依赖关系表达弱
- 容易出现工具循环

所以这个项目在复杂任务上其实已经没有继续坚持纯 ReAct 了。

#### 项目里哪些地方已经不是纯 ReAct

1. DeepSearch

位于：

- [deepsearch/graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/graph.py)
- [deepsearch/stream_graph.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/deepsearch/stream_graph.py)

这里已经明显是：

- graph workflow
- reflection loop
- loop count 控制
- query generation -> web research -> reflection -> finalize

2. LingSeek

位于：

- [lingseek/agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/lingseek/agent.py)

它会生成任务图、展示依赖关系，更接近：

- plan decomposition
- task graph execution

所以更准确地说，项目是在不同子系统里混用了不同范式。

#### 如果问“为什么不用纯 Plan-and-Execute”

你可以说：

因为 Plan-and-Execute 也不是银弹。它的代价包括：

- 首轮需要先生成计划，首 token 更慢
- 对简单任务反而浪费 token
- 计划本身可能不稳定，甚至过度规划
- 工程实现和调试复杂度更高

因此更合理的做法是：

- 简单任务用 ReAct
- 长任务用 Plan / Graph

这其实也是很多成熟 Agent 系统的真实做法。

#### 适合背诵的回答

> 这个项目并不是全站只用 ReAct，而是按任务复杂度做分层选型。主链路偏 ReAct，因为高频对话和普通工具调用场景更需要响应快、流式好、实现轻；但在 DeepSearch 和 LingSeek 这类复杂任务里，项目已经引入了 graph workflow、reflection loop 和任务图分解，更接近 Plan-and-Execute 或 Graph-based Agent。所以我的理解不是“ReAct 对、Plan-and-Execute 错”，而是短任务优先 ReAct，长任务和研究型任务优先显式工作流。 

### 3.4 为什么采用多 Agent 结构？

#### 直接结论

采用多 Agent 结构的核心原因不是“听起来高级”，而是为了职责解耦、能力复用、复杂任务拆分和系统扩展。

#### 这个项目里的多 Agent 不是空谈

从代码看，项目里确实存在多种 Agent：

- 通用对话 Agent
- MCP Agent
- Skill Agent
- Mars Agent
- DeepSearch Agent
- LingSeek Agent

而且一个很关键的点是：它不是所有 Agent 平行各干各的，而是会把某些 Agent 再包装成上层 Agent 可调用的工具，也就是“Agent as Tool”。

相关代码在：

- [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py)
- [mcp_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/mcp_agent.py)
- [skill_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/skill_agent.py)

#### 为什么这有价值

1. 职责边界更清晰

例如：

- 通用 Agent 负责对话和整体协调
- MCP Agent 负责远程能力调用
- Skill Agent 负责封装某类复合技能

如果都放在一个 Agent 里，Prompt 会越来越大，工具越来越乱，状态越来越难管。

2. 更容易复用

某个 Skill Agent 一旦封装好，就可以在多个上层 Agent 里复用，而不是每个地方都重复写一套 prompt + tool wiring。

3. 更容易扩展

新增一个复杂能力时，不一定要改主 Agent，只要新增一个 Agent 模块，再把它挂载成 tool 即可。

4. 更适合复杂任务分工

比如：

- 一个 Agent 负责规划
- 一个 Agent 负责检索
- 一个 Agent 负责写作
- 一个 Agent 负责校验

这比单 Agent 同时扮演所有角色更稳定。

#### 多 Agent 的代价也要说

如果面试官问“多 Agent 有什么坏处”，要敢于说：

- 上下文传递更复杂
- 协调成本更高
- 错误链更长
- 调试更难
- token 成本更高

所以不是越多越好，而是看是否真的存在明确职责边界。

#### 适合背诵的回答

> 采用多 Agent 结构，核心不是为了“炫技”，而是为了解决职责耦合问题。这个项目里，一个重要设计是把 MCP Agent、Skill Agent 进一步封装成上层 Agent 可调用的工具，也就是 Agent as Tool。这样做的好处是能力边界清晰、复杂模块可复用、扩展性更强，而且更适合把复杂任务拆成不同角色来完成。当然，多 Agent 也会带来上下文传递和调试复杂度上升的问题，所以我的原则是：只有当职责边界足够清晰时，多 Agent 才值得。 

### 3.5 多 Agent 有哪些架构范式？应用场景分别是什么？

这题如果答得太短，面试官会觉得你只是背了几个名词。更好的答法是按“范式 + 适用场景 + 取舍”来讲。

#### 1. Router / Dispatcher 模式

特点：

- 先做意图识别
- 再把请求路由给最适合的 Agent

适合：

- 多领域助手
- 客服分流
- 一个系统里有多个专家 Agent

优点：

- 路由清晰
- 不会让所有 Agent 都参与

缺点：

- 路由错误会直接影响最终结果

#### 2. Supervisor-Worker 模式

特点：

- 一个总控 Agent 负责任务拆分
- 多个 Worker Agent 负责子任务执行
- 最后由 Supervisor 汇总结果

适合：

- 多步骤任务
- 报告生成
- 多工具协作

优点：

- 分工明确
- 易于并行

缺点：

- 汇总和协调成本高

#### 3. Agent as Tool 模式

特点：

- 下层 Agent 被包装成上层 Agent 的一个工具

适合：

- 封装复杂能力
- 专家模块复用
- 平台型 Agent 系统

这个项目就很接近这种范式。

优点：

- 上层保持统一编排，下层保留专业能力

缺点：

- 需要做好输入输出边界和上下文裁剪

#### 4. Plan-and-Execute 模式

特点：

- 先规划
- 再按计划执行

适合：

- 长流程任务
- 需要显式依赖关系的任务
- 结果稳定性比响应速度更重要的场景

优点：

- 任务路径更清晰
- 可控性更强

缺点：

- 首轮更慢
- 规划有时过度

#### 5. Graph Workflow 模式

特点：

- 节点、边、条件跳转都显式定义
- 可以做循环、并行、反思、回退

适合：

- 深度研究
- 工作流自动化
- 多跳推理
- 对流程可解释性要求高的场景

这个项目里的 DeepSearch、LingSeek 已经有这个方向。

#### 6. Debate / Critic 模式

特点：

- 多个 Agent 互相辩论、校验、打分

适合：

- 高准确率推理
- 审查和校验类任务

优点：

- 有利于降低单模型偏差

缺点：

- token 成本很高

#### 7. Blackboard / Shared Memory 模式

特点：

- 多个 Agent 共享一个状态板、任务板或记忆池

适合：

- 协同写作
- 长流程协作
- 多角色共享事实

优点：

- 协作灵活

缺点：

- 状态一致性难维护

#### 适合背诵的回答

> 多 Agent 常见范式可以分成几类：第一类是 Router 模式，适合多领域分流；第二类是 Supervisor-Worker，适合复杂任务拆解和并行执行；第三类是 Agent as Tool，把专家 Agent 封装成工具，适合能力平台化，这个项目就有这种设计；第四类是 Plan-and-Execute，适合长任务和显式依赖；第五类是 Graph Workflow，适合深度研究和可解释流程；第六类是 Debate 或 Critic，适合高准确率审查；第七类是 Shared Memory 或 Blackboard，适合多角色共享状态。我的理解是，不同范式没有绝对优劣，关键是要看任务长度、稳定性要求、可解释性要求和成本约束。 

## 4. MCP、A2A、Skill、Function Call

### 4.1 MCP 与 A2A 是什么？它们之间传输信息的格式是什么？

#### 先分开解释

##### MCP 是什么

MCP，Model Context Protocol，本质上是“模型接工具、资源和 prompt 的标准协议”。

它的目标是把下面这些东西统一起来：

- 工具描述
- 参数 schema
- 资源访问
- prompt 模板
- 会话调用协议

在这个项目里，MCP 是主业务链路的一部分，已经做得比较完整。

相关代码在：

- [sessions.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/sessions.py)
- [multi_client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/multi_client.py)
- [tools.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/load_mcp/tools.py)
- [manager.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/mcp/manager.py)

##### A2A 是什么

A2A 可以理解为 Agent-to-Agent 协议，核心关注的是：

- 一个 Agent 如何发现另一个 Agent 的能力
- 如何给对方发消息
- 如何拿到对方的流式回复或任务状态

在这个项目里，A2A 不是主线能力，只在测试目录里有探索性样例：

- [test_a2a/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/client.py)
- [test_a2a/main.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/main.py)

所以如果面试官问“项目里 MCP 和 A2A 都用了么”，要实话实说：

> MCP 是主链路能力，A2A 在这个项目里更多是测试和探索，不是正式业务主路径。

#### 它们分别传什么

##### MCP 传的是什么

MCP 更偏：

- tool schema
- tool call arguments
- resources
- prompts
- tool result

在这个项目里，MCP tool 会被转换为 LangChain Tool，其关键元数据包括：

- `name`
- `description`
- `inputSchema`

调用时最终走：

- `session.call_tool(tool.name, arguments)`

返回结果则会被 `_convert_call_tool_result(...)` 处理成：

- 文本内容 `TextContent`
- 非文本内容，例如 `ImageContent`、`EmbeddedResource`

也就是说，MCP 传输的核心是“结构化 schema + 协议消息”。

##### A2A 传的是什么

从 [test_a2a/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/test/test_a2a/client.py) 可以看到，它构造的是：

- `SendStreamingMessageRequest`
- `MessageSendParams`
- `Message`
- `Role`
- `Part`
- `TextPart`

这说明 A2A 的消息格式更像一个标准化消息对象：

- 有 role
- 有 message_id
- 有 parts

`parts` 里可以装文本，也可以扩展其他类型内容。

#### 两者的区别怎么讲最专业

你可以这么区分：

- MCP 更偏“模型如何接标准化外部能力”
- A2A 更偏“Agent 如何与 Agent 协同通信”

换句话说：

- MCP 解决的是工具和资源的标准接入
- A2A 解决的是智能体之间的标准交互

#### 适合背诵的回答

> MCP 和 A2A 虽然都属于 AI 系统里的协议层，但关注点不一样。MCP 更偏模型接工具、资源和 prompt 的标准协议，在这个项目里是正式主链路能力，支持 stdio、sse、streamable_http、websocket 等多种 transport，并且会把远程 MCP tool 动态转换成 LangChain Tool；A2A 更偏 Agent-to-Agent 的通信协议，在这个仓库里主要还是测试样例。格式上，MCP 传输的是结构化 schema 和 tool call 消息，比如 `name`、`description`、`inputSchema` 以及 `call_tool(arguments)`；A2A 更像标准消息对象，包含 `Message`、`Role`、`Part`、`TextPart` 等结构，用于 Agent 间发送流式消息。 

### 4.2 长短期记忆怎么存储的？

#### 先给结论

这个项目没有把“短期记忆”和“长期记忆”设计成两套非常教科书式的独立模块，但从实现上可以清晰地区分：

- 短期记忆：当前对话上下文、当前 run/dialog 的消息历史
- 长期记忆：`AsyncMemory` 中持久化存储的事实记忆

#### 短期记忆是什么

短期记忆本质上是：

- 当前 prompt 窗口中的 messages
- 当前对话 session 的上下文
- 当前 run / dialog 内部状态

它的特点是：

- 生命周期短
- 直接参与本轮推理
- 不一定持久保留

#### 长期记忆是什么

长期记忆更接近：

- 用户稳定偏好
- 可复用事实
- 历史会话中沉淀下来的结构化记忆

这个项目中由：

- [memory/client.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/services/memory/client.py)

承担，底层默认走：

- `Chroma`

并按 metadata 做范围隔离：

- `user_id`
- `agent_id`
- `run_id`
- `actor_id`

#### 这个项目的长期记忆不是简单存文本

这是它比较亮眼的地方。

`AsyncMemory.add(...)` 在 `infer=True` 时，不会直接把原始对话塞进向量库，而是：

1. 解析 messages
2. 调 LLM 抽取 `facts`
3. 对新 facts 做 embedding
4. 检索相似旧记忆
5. 再让模型决定是：
   - `ADD`
   - `UPDATE`
   - `DELETE`
   - `NONE`
6. 最终把结果写入向量库和历史表

所以它更像“事实记忆管理”，而不是“聊天记录仓库”。

#### 存储形式有哪些

1. 向量存储

用于语义检索记忆

2. Metadata

用于范围控制和记忆标识

3. 历史表

用于记录 ADD / UPDATE / DELETE 历史

#### 项目现状的不足

要实话实说：

- 还没做经典的 STM/LTM 分层架构
- 没有显式的记忆重要性和遗忘机制
- 没有长期记忆自动压缩与归纳

#### 适合背诵的回答

> 这个项目里短期记忆主要是当前会话和当前 run 的消息上下文，直接进入 prompt；长期记忆则由 `AsyncMemory` 持久化到向量存储中，默认底层是 Chroma，并通过 `user_id`、`agent_id`、`run_id` 等 metadata 做范围隔离。比较重要的一点是，项目的长期记忆不是把聊天记录原样塞进向量库，而是先让模型抽取 facts，再结合历史记忆判断是 ADD、UPDATE、DELETE 还是 NONE，所以它更像一个持续更新的事实记忆系统。 

### 4.3 skill 和 function call 有什么区别？

#### 先给一句话定义

- function call 更像“调用一个原子函数”
- skill 更像“调用一个封装好的复合能力模块”

#### Function call 的特点

function call 通常具备这些特征：

- 单次调用
- 输入输出 schema 明确
- 一次动作就完成
- 更偏原子能力

例如：

- 查天气
- 搜索网页
- 发 HTTP 请求
- 执行数据库查询

#### Skill 的特点

skill 更像一种“高阶能力封装”：

- 背后可能不止一个函数
- 可能带自己的 prompt
- 可能有自己的工具集
- 可能包含多步内部逻辑

在这个项目里，skill 不是单纯一个函数，而是有：

- `SkillAgent`

相关代码在：

- [skill_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/skill_agent.py)
- [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py)

这里 skill 的典型落地是：

- 一个 Skill Agent 被包装成上层 Agent 的 tool

这意味着 skill 本质上是“Agent 级别的能力封装”，不是简单 function。

#### 区别从工程角度怎么讲

1. 粒度不同

- function call：原子动作
- skill：复合动作

2. 责任边界不同

- function call：只负责执行一个能力
- skill：负责完成某类任务目标

3. 可复用方式不同

- function call 复用的是函数
- skill 复用的是能力模块

4. Prompt / 状态依赖不同

- function call 往往不需要独立 prompt
- skill 往往有自己的执行上下文和提示词

#### 面试时最好怎么说

> 在我理解里，function call 是“调用一个函数”，skill 是“调用一个小专家”。function call 更偏原子能力，输入输出 schema 清晰；skill 更偏复合能力，背后可能有自己的 prompt、工具和多步逻辑。这个项目里 skill 的典型实现就是 Skill Agent as Tool，所以它不是单一 API，而是一个被上层 Agent 调用的能力模块。 

## 5. 记忆、通信、工具上下文与容灾

### 5.1 关于通信，你是如何处理的？如何平衡性能与质量？

这个问题建议从“用户侧通信”和“系统内部通信”两层回答。

#### 第一层：用户侧通信

项目主链路使用的是：

- FastAPI `StreamingResponse`
- `text/event-stream`
- 前端 `fetch-event-source`

也就是标准 SSE 流式通信。

为什么这里选 SSE？

因为场景是：

- 服务端不断向前端输出 token / chunk
- 前端需要持续渲染
- 交互模式是“服务端单向流式输出”为主

SSE 的优势是：

- 实现简单
- 对 HTTP 友好
- 比轮询体验更好
- 对这种“持续推 token”场景非常合适

#### 第一层：系统内部通信

项目内部大量使用：

- `asyncio`
- `asyncio.gather`
- `Queue`
- 流式 chunk 事件

例如：

- RAG 的 embedding 批处理
- MCP 多工具并发调用
- Mars 中 reasoning 流和 agent 输出流并行组织

这说明系统在内部是偏异步协作模型，而不是同步串行阻塞。

#### 性能和质量如何平衡

这个问题不能只答“用异步”，还要讲策略：

1. 首 token 优先

通过流式返回，让用户先看到输出，缩短感知延迟。

2. 不盲目并发

并不是所有步骤都并发。比如：

- 检索链路要按依赖执行
- 只有能并行的步骤才 `gather`

3. 高成本步骤只在必要时触发

例如：

- Query Rewrite
- Hybrid Retrieval
- Rerank

这些虽然提高质量，但也会增加时延，所以要按业务需要启用。

4. 思考流和结果流拆通道

Mars 的 reasoning 可视化就是一个例子，后端把：

- `reasoning_chunk`
- `response_chunk`

分开传，既保留体验，又能控制最终回答展示。

#### 适合背诵的回答

> 我会把通信分成用户侧和系统侧两层。用户侧，这个项目主要用 SSE，也就是 FastAPI 的 `StreamingResponse` 加 `text/event-stream`，前端用 `fetch-event-source` 消费，核心目的是尽快把首 token 推给用户，降低感知延迟；系统侧则大量使用 asyncio、gather 和事件队列来组织 embedding、检索、工具调用和流式 chunk。性能和质量的平衡点在于，不是盲目并发所有步骤，而是把高成本但高收益的步骤，比如 rewrite、hybrid retrieval、rerank，放在真正需要时才触发，同时通过流式输出提升交互体验。 

### 5.2 关于工具调用和上下文管理，有什么处理方式？

这个问题非常适合结合项目来讲，因为项目里已经明显意识到“工具太多会撑爆上下文”的问题。

#### 问题本质是什么

工具调用和上下文管理的痛点主要有两个：

1. 工具太多

- Prompt 太长
- 工具描述占满上下文
- 模型不会选，或者乱选

2. 工具太少

- 问题解决不了
- 覆盖面不够
- Agent 无法完成复杂任务

所以这其实是在做一个平衡：

- 工具暴露多少给模型
- 什么时候暴露
- 如何让模型更容易选对

#### 项目里已有的设计

在 [general_agent.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/core/agents/general_agent.py) 中，已经能看到这方面的思路：

- `MAX_TOOLS_SIZE = 10`
- 设计了 `search_available_tools(...)`

这个搜索工具的逻辑是：

1. 当工具太多时，不把所有工具直接绑给模型
2. 先只给一个“工具搜索器”
3. 让模型先按关键词找相关工具
4. 再把相关工具通过 `Command(update={"available_tools": ...})` 动态写入 state

这本质上是在做“工具检索”。

这是一个很好的设计，因为它把：

- 工具选择问题
- 上下文压缩问题
- 大工具池管理问题

串在一起解决了。

#### 但项目也有一个现实情况

当前主链路里，这套“先搜索再暴露”的思路还没有完全发挥出来。

因为 `setup_react_agent()` 实际上仍然偏向：

- 直接把 `self.tools + self.mcp_agent_as_tools + self.skill_agent_as_tools` 绑上去

也就是说，项目已经意识到问题，并设计了优化方向，但还没有完全产品化为默认主路径。

#### 如果是我来优化，我会做什么

1. 工具分层

- 核心高频工具常驻
- 长尾工具走工具检索

2. 先路由再暴露

先根据用户意图做粗分类，再只暴露一个子集工具。

3. 工具描述压缩

不是把冗长文档全塞给模型，而是保留：

- 功能关键词
- 关键输入
- 关键适用场景

4. 工具反馈闭环

统计：

- 命中率
- 调用成功率
- 误调用率
- 被选择但无效果的比例

5. Tool-as-Agent

对复杂能力，不直接暴露底层几十个函数，而是封装成 Skill Agent 或 MCP Agent，再作为高阶工具暴露。

#### 面试推荐说法

> 工具调用和上下文管理的核心矛盾是：工具多了，上下文被撑爆，模型不会选；工具少了，又解决不了问题。这个项目里已经有一个比较好的设计思路，就是在 `GeneralAgent` 里提供 `search_available_tools`，先让模型检索相关工具，再通过 `Command(update={"available_tools": ...})` 动态暴露子集工具，本质上是在做工具检索和上下文裁剪。不过当前主路径里这套能力还没有完全成为默认流程，所以如果继续优化，我会把工具分层、意图路由、描述压缩和动态暴露做成正式主链路。 

### 5.3 关于容灾，你是如何解决的？

这道题是综合题，最好的答法是“按层次回答”，不要一上来就只说重试。

#### 第一层：任务状态可追踪

项目在知识库文件处理上就已经有任务状态：

- `process`
- `success`
- `fail`

见：

- [knowledge_file.py](/e:/Codes/study-projects/AgentChat/src/backend/agentchat/api/services/knowledge_file.py)

这说明最基本的容灾意识已经有了：

- 出问题时不是静默失败
- 可以知道失败发生在哪个阶段

#### 第二层：工具和 Agent 异常兜底

在多个 Agent middleware 里，工具调用异常不会直接把整个流程打崩，而是：

- catch 住异常
- 生成错误事件
- 转成 `ToolMessage`

这类设计的意义是：

- 让 Agent 仍然有机会做降级回答
- 把错误反馈给上层，而不是直接崩溃

#### 第三层：超时和取消

项目里部分场景已经使用：

- `asyncio.wait_for`
- `cancel()`

来限制任务无限挂起。

这属于执行层容灾。

#### 第四层：配置校验和 fail fast

MCP session 创建时，如果配置缺少关键字段，会直接 fail fast。比如：

- SSE 缺 `url`
- stdio 缺 `command` 或 `args`

就直接报错，不让错误一路拖到运行期深处。

这是一种很重要但常被忽视的容灾思路：越早失败越好。

#### 第五层：资源侧降压

项目里还有一些“降低异常扩散面”的设计，例如：

- Milvus collection 懒加载
- MCP session 按需创建

这有助于避免资源常驻过多、长期连接过多，降低系统脆弱性。

#### 这个项目还缺什么

如果面试官追问“这就够了吗”，你要明确说：

还不够。

更完整的容灾体系我会继续补：

1. 重试和退避

对模型、检索、工具调用做有上限的重试，并带指数退避。

2. 熔断

某个工具或 MCP Server 连续失败时，短期熔断，避免拖垮整条链路。

3. 降级策略

例如：

- Milvus 不可用时回退 ES
- summary 检索不够时回退 content
- reasoning model 不可用时只保留基础回答链路

4. 监控和告警

要监控：

- 调用成功率
- 平均时延
- 工具失败率
- token 消耗
- 检索命中率

5. 可恢复任务

对于长任务，需要状态持久化和断点恢复能力。

#### 适合背诵的回答

> 这类 AI 系统的容灾我会按五层来看。第一层是状态可追踪，这个项目在知识库处理里已经有 `process/success/fail` 状态；第二层是执行异常兜底，工具调用异常不会直接把整个 Agent 打崩，而是会被转成错误事件或 ToolMessage；第三层是超时和取消，部分场景已经用了 `wait_for + cancel`；第四层是 fail fast，比如 MCP session 创建时如果配置不合法会立刻报错；第五层是资源侧降压，比如 Milvus collection 懒加载、MCP session 按需创建。再往上，如果做完整容灾体系，我会继续补重试、熔断、降级、监控和长任务恢复机制。 

## 6. 高频收束回答

### 6.1 如果面试官让你用一段话概括这个项目的技术亮点

> 这个项目的亮点不在单个模型，而在整条 AI 应用链路的工程化设计。知识库侧，它不是简单 split text，而是做了按文件类型解析、PDF 转 Markdown、标题层级切块、摘要向量和正文向量双路召回、Milvus + ES 混合检索以及 rerank；Agent 侧，它主链路偏 ReAct，但在 DeepSearch 和 LingSeek 上已经引入了 graph workflow 和任务图分解；MCP 侧，支持多 transport、动态发现远程工具并转换成 LangChain Tool；记忆侧，已经具备持久化事实记忆和增删改逻辑，而不是简单堆聊天记录。所以我会把它理解为一个具备知识、工具、记忆和模型调度能力的 Agent 平台，而不是单模型聊天应用。 

### 6.2 如果面试官问你“你最认可这个项目哪几个点”

你可以说：

1. RAG 前处理做得比较像样，不是粗暴切块
2. MCP 已经形成了平台化扩展能力，不是 demo 级接法
3. 记忆不是 append-only，而是有 facts 抽取和增删改
4. 对复杂任务没有死抱纯 ReAct，而是已经开始往 graph workflow 走

### 6.3 如果面试官问“你觉得这个项目最大的不足是什么”

可以这样说：

1. 工具动态裁剪设计虽有雏形，但主链路还没完全落地
2. RAG 评估有离线脚本，但还没有完整的持续评测体系
3. 记忆系统有基础能力，但还不是成熟的长期记忆架构
4. 容灾已经有基础防护，但距离完整熔断、降级、监控体系还有距离

这种答法会显得你既理解项目，也有批判性判断。
