# AgentChat 项目向量数据库使用详解 (Elasticsearch + Milvus + Chroma)

## 目录
1. [项目架构概述](#1-项目架构概述)
2. [Elasticsearch 详解](#2-elasticsearch-详解)
3. [Milvus 详解](#3-milvus-详解)
4. [Chroma 详解](#4-chroma-详解)
5. [混合检索架构](#5-混合检索架构)
6. [面试题与答案](#6-面试题与答案)

---

## 1. 项目架构概述

### 1.1 三大数据库的角色

| 数据库 | 用途 | 存储内容 | 代码位置 |
|--------|------|----------|----------|
| **Elasticsearch** | 关键词搜索 | RAG 文档内容 | [es_client.py](src/backend/agentchat/services/rag/es_client.py) |
| **Milvus** | 向量相似度搜索 | RAG 文档向量 | [milvus_client.py](src/backend/agentchat/services/rag/vector_db/milvus_client.py) |
| **Chroma (RAG)** | 向量相似度搜索 | RAG 文档向量（可选替代Milvus） | [chroma_client.py](src/backend/agentchat/services/rag/vector_db/chroma_client.py) |
| **Chroma (Memory)** | 记忆存储 | 对话记忆向量 | [chroma.py](src/backend/agentchat/services/memory/vector_stores/chroma.py) |

### 1.2 配置信息

**配置文件**：[config.yaml](src/backend/agentchat/config.yaml)

```yaml
# RAG 配置
rag:
  enable_elasticsearch: True  # 是否启用 ES
  elasticsearch:
    hosts: "http://127.0.0.1:9200"

  vector_db:
    host: "127.0.0.1"
    port: "19530"
    mode: "standalone"  # standalone (Milvus), lite (轻量Milvus), chroma (ChromaDB)

# 记忆配置
default_config:
  memory_collection_name: "memory"
```

### 1.3 数据流转图

```
                        ┌─────────────────────────────────────────┐
                        │           文档上传流程                    │
                        └─────────────────────────────────────────┘
                                              │
                                              ▼
                        ┌─────────────────────────────────────────┐
                        │         Parser (文档解析切分)            │
                        │         → ChunkModel 列表               │
                        └─────────────────────────────────────────┘
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        │                     │                     │
                        ▼                     ▼                     ▼
              ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
              │  Elasticsearch  │   │     Milvus      │   │ Chroma (RAG)    │
              │  (关键词索引)     │   │  (向量存储)      │   │ (向量存储-备选) │
              └─────────────────┘   └─────────────────┘   └─────────────────┘

                        ┌─────────────────────────────────────────┐
                        │           RAG 查询流程                    │
                        └─────────────────────────────────────────┘
                                              │
                                              ▼
                        ┌─────────────────────────────────────────┐
                        │         Query Rewrite (查询重写)         │
                        └─────────────────────────────────────────┘
                                              │
                        ┌─────────────────────┬─────────────────────┐
                        │                     │                     │
                        ▼                     ▼                     ▼
              ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
              │  Elasticsearch  │   │     Milvus      │   │ Chroma (RAG)    │
              │  关键词召回       │   │  向量召回         │   │  向量召回-备选   │
              └─────────────────┘   └─────────────────┘   └─────────────────┘
                        │                     │                     │
                        └─────────────────────┼─────────────────────┘
                                              │
                                              ▼
                        ┌─────────────────────────────────────────┐
                        │         Rerank (重排序)                   │
                        └─────────────────────────────────────────┘
                                              │
                                              ▼
                        ┌─────────────────────────────────────────┐
                        │         Filter (过滤) → LLM             │
                        └─────────────────────────────────────────┘
```

---

## 2. Elasticsearch 详解

### 2.1 核心代码：ESClient

**文件**：[es_client.py](src/backend/agentchat/services/rag/es_client.py)

```python
class ESClient:
    def __init__(self):
        self.client = Elasticsearch(hosts=app_settings.rag.elasticsearch.get('hosts'))
```

**主要方法**：

| 方法 | 功能 |
|------|------|
| `insert_documents()` | 批量插入文档块 |
| `search_documents()` | 基于 content 字段搜索 |
| `search_documents_summary()` | 基于 summary 字段搜索 |
| `delete_documents()` | 根据 file_id 删除文档 |

### 2.2 索引 Mapping 配置

**文件**：[es_index.py](src/backend/agentchat/config/es_index.py)

```json
{
  "mappings": {
    "properties": {
      "chunk_id": { "type": "keyword" },
      "content": { "type": "text", "analyzer": "ik_analyzer" },
      "summary": { "type": "text", "analyzer": "ik_analyzer" },
      "file_id": { "type": "keyword" },
      "knowledge_id": { "type": "keyword" },
      "file_name": { "type": "keyword" },
      "update_time": { "type": "date" }
    }
  }
}
```

### 2.3 搜索查询模板

**内容搜索**：
```json
{
  "size": 10,
  "timeout": "3s",
  "query": {
    "match": {
      "content": {
        "query": "{query}",
        "analyzer": "ik_smart",
        "operator": "and",
        "minimum_should_match": "75%",
        "fuzziness": "AUTO",
        "boost": 2.0
      }
    }
  }
}
```

### 2.4 数据模型

```python
class ChunkModel:
    def __init__(self, chunk_id, content, file_id, file_name,
                 update_time, knowledge_id, summary=""):
        self.chunk_id = chunk_id
        self.content = content
        self.file_id = file_id
        self.file_name = file_name
        self.update_time = update_time
        self.knowledge_id = knowledge_id
        self.summary = summary
```

---

## 3. Milvus 详解

### 3.1 核心代码：MilvusClient

**文件**：[milvus_client.py](src/backend/agentchat/services/rag/vector_db/milvus_client.py)

```python
class MilvusClient:
    def __init__(self, **kwargs):
        self.milvus_host = app_settings.rag.vector_db.get('host')
        self.milvus_port = app_settings.rag.vector_db.get('port')
        self.collections: Dict[str, Collection] = {}
        self._connect()
```

### 3.2 集合 Schema 设计

```python
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=256),
    FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=2048),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),      # 内容向量
    FieldSchema(name="summary", dtype=DataType.VARCHAR, max_length=1024),
    FieldSchema(name="embedding_summary", dtype=DataType.FLOAT_VECTOR, dim=1024),  # 摘要向量
    FieldSchema(name="file_id", dtype=DataType.VARCHAR, max_length=128),
    FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=256),
    FieldSchema(name="knowledge_id", dtype=DataType.VARCHAR, max_length=128),
    FieldSchema(name="update_time", dtype=DataType.VARCHAR, max_length=128),
]
```

### 3.3 索引配置

```python
index_params = {
    "index_type": "IVF_FLAT",
    "metric_type": "L2",
    "params": {"nlist": 128}
}
```

### 3.4 搜索实现

```python
async def search(self, query: str, collection_name: str, top_k: int = 10):
    # 1. 生成查询向量
    query_embedding = await get_embedding(query)

    # 2. 定义搜索参数
    search_params = {
        "metric_type": "L2",
        "params": {"nprobe": 16}
    }

    # 3. 执行搜索
    results = collection.search(
        data=[query_embedding],
        anns_field="embedding",      # 指定搜索的向量字段
        param=search_params,
        limit=top_k,
        output_fields=["content", "chunk_id", "summary", ...]
    )

    # 4. 格式化结果
    for hit in results[0]:
        documents.append(SearchModel(
            content=hit.entity.content,
            score=hit.distance  # L2 距离
        ))
```

---

## 4. Chroma 详解

### 4.1 两套 Chroma 的区别

| 用途 | 代码位置 | 数据路径 | 作用 |
|------|----------|----------|------|
| **RAG Chroma** | [chroma_client.py](src/backend/agentchat/services/rag/vector_db/chroma_client.py) | `./vector_db` | 替代 Milvus 存储 RAG 文档向量 |
| **Memory Chroma** | [chroma.py](src/backend/agentchat/services/memory/vector_stores/chroma.py) | `memory_db` | 存储对话记忆向量 |

### 4.2 RAG Chroma (chroma_client.py)

**文件**：[chroma_client.py](src/backend/agentchat/services/rag/vector_db/chroma_client.py)

```python
class ChromaClient:
    def __init__(self, **kwargs):
        self.collections: Dict[str, chromadb.Collection] = {}
        self.client = chromadb.PersistentClient(path="./vector_db")  # 数据路径

    async def create_collection(self, collection_name: str):
        collection = self.client.create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}  # 使用余弦相似度
        )
```

**集合创建**：
```python
collection = self.client.create_collection(
    name=collection_name,
    metadata={"hnsw:space": "cosine"}  # cosine/L2/ip
)
```

**数据插入**：
```python
# 文档 + 元数据 + 向量
collection.add(
    ids=ids,
    documents=documents,
    embeddings=embeddings,
    metadatas=metadatas  # 包含 chunk_id, file_id, is_summary 等
)
```

**搜索实现**：
```python
results = collection.query(
    query_embeddings=[query_embedding],
    n_results=top_k,
    include=["metadatas", "documents", "distances"],
    where={"is_summary": True}  # 可选过滤条件
)

# 距离转换为相似度分数
score = 1.0 - results['distances'][0][i]
```

### 4.3 Memory Chroma (chroma.py)

**文件**：[chroma.py](src/backend/agentchat/services/memory/vector_stores/chroma.py)

```python
class ChromaDB(VectorStoreBase):
    def __init__(self, collection_name: str, path: Optional[str] = None):
        if path is None:
            path = "memory_db"  # 数据路径

        self.settings = Settings(
            anonymized_telemetry=False,
            persist_directory=path,
            is_persistent=True
        )
        self.client = chromadb.Client(self.settings)
```

**Memory 服务集成**：

**文件**：[client.py](src/backend/agentchat/services/memory/client.py)

```python
class AsyncMemory(MemoryBase):
    def __init__(self):
        self.vector_store = VectorStoreManager.get_chroma_vector()  # 获取 ChromaDB 实例
```

**VectorStoreManager**：

**文件**：[vector_stores/__init__.py](src/backend/agentchat/services/memory/vector_stores/__init__.py)

```python
class VectorStoreManager:
    @classmethod
    def get_chroma_vector(cls):
        return ChromaDB(
            collection_name=app_settings.default_config.get("memory_collection_name")
        )
```

### 4.4 Chroma 数据结构

```python
# Memory 存储的数据结构
metadata = {
    "data": "记忆内容",           # 实际记忆文本
    "hash": "md5哈希值",          # 内容哈希
    "created_at": "创建时间",      # ISO 格式时间
    "updated_at": "更新时间",      # ISO 格式时间
    "user_id": "用户ID",
    "agent_id": "Agent ID",
    "run_id": "Run ID",
    "actor_id": "发言者ID",
    "role": "角色(user/assistant)"
}
```

### 4.5 SQLite3 文件说明

Chroma 默认使用 SQLite 作为底层存储：

| 路径 | 用途 | 来源 |
|------|------|------|
| `src/backend/memory_db/chroma.sqlite3` | Memory 记忆存储 | [chroma.py](src/backend/agentchat/services/memory/vector_stores/chroma.py) 中 `path="memory_db"` |
| `src/backend/vector_db/chroma.sqlite3` | RAG 文档向量存储 | [chroma_client.py](src/backend/agentchat/services/rag/vector_db/chroma_client.py) 中 `path="./vector_db"` |

**生成时机**：
- 当 `ChromaDB` 或 `ChromaClient` 首次初始化且指定的 `persist_directory` 目录不存在时，Chroma 会自动创建 SQLite 数据库文件
- Chroma 的 `PersistentClient` 会自动持久化数据到指定目录

---

## 5. 混合检索架构

### 5.1 检索入口：RagHandler

**文件**：[rag_handler.py](src/backend/agentchat/services/rag_handler.py)

```python
class RagHandler:
    @classmethod
    async def mix_retrival_documents(cls, query_list, knowledges_id, search_field):
        if app_settings.rag.enable_elasticsearch:
            # ES + Milvus/Chroma 混合检索
            es_documents, milvus_documents = await MixRetrival.mix_retrival_documents(...)
        else:
            # 仅使用 Milvus/Chroma
            all_documents = await MixRetrival.retrival_milvus_documents(...)
```

### 5.2 混合检索实现

**文件**：[retrieval.py](src/backend/agentchat/services/retrieval.py)

```python
class MixRetrival:
    @classmethod
    async def mix_retrival_documents(cls, query_list, knowledges_id, search_field):
        es_documents = []
        milvus_documents = []

        for query in query_list:
            # 并行检索
            es_documents += await cls.retrival_es_documents(query, knowledges_id, search_field)
            milvus_documents += await cls.retrival_milvus_documents(query, knowledges_id, search_field)

        return es_documents, milvus_documents
```

### 5.3 结果合并策略

```python
# 1. 各自排序
es_documents.sort(key=lambda x: x.score, reverse=True)
milvus_documents.sort(key=lambda x: x.score, reverse=True)
all_documents = es_documents + milvus_documents

# 2. 合并去重
documents = []
seen_chunk_ids = set()
all_documents.sort(key=lambda x: x.score, reverse=True)

for doc in all_documents:
    if doc.chunk_id not in seen_chunk_ids:
        seen_chunk_ids.add(doc.chunk_id)
        documents.append(doc)
        if len(documents) >= 10:
            break
```

### 5.4 向量数据库选择机制

**文件**：[vector_db/__init__.py](src/backend/agentchat/services/rag/vector_db/__init__.py)

```python
milvus_client = None
if app_settings.rag.vector_db.get("mode") == "chroma":
    milvus_client = ChromaClient()      # 使用 Chroma
elif app_settings.rag.vector_db.get("mode") == "lite":
    milvus_client = MilvusLiteClient()  # 使用轻量 Milvus
else:
    milvus_client = MilvusClient()      # 默认使用 Milvus
```

---

## 6. 用户隔离与多租户机制

### 6.1 概述：两套隔离策略

项目中存在**两套独立的用户隔离机制**，分别用于 RAG 系统和 Memory 系统：

| 系统 | 隔离方式 | 标识字段 | 隔离粒度 |
|------|----------|----------|----------|
| **RAG** | Collection/Index 隔离 | `knowledge_id` | 知识库级别（可属于用户或群组） |
| **Memory** | Metadata 过滤隔离 | `user_id` + `agent_id` + `run_id` | 会话级别（多维度） |

---

### 6.2 RAG 系统的用户隔离

#### 6.2.1 核心机制：按 `knowledge_id` 分集合

**设计思想**：每个知识库（Knowledge Base）对应一个独立的 Collection（Milvus/Chroma）或 Index（ES）。

**数据模型**：

```python
class ChunkModel:
    def __init__(self, chunk_id, content, file_id, file_name,
                 update_time, knowledge_id, summary=""):
        self.chunk_id = chunk_id      # 文档块唯一ID
        self.content = content        # 文档内容
        self.file_id = file_id        # 所属文件ID
        self.file_name = file_name    # 文件名
        self.update_time = update_time # 更新时间
        self.knowledge_id = knowledge_id # ★ 知识库ID（用于隔离）
        self.summary = summary        # 文档摘要
```

#### 6.2.2 文档上传时的隔离

**文件**：[parser.py](src/backend/agentchat/services/rag/parser.py)

```python
async def parse_doc_into_chunks(cls, file_id, file_path, knowledge_id, ...):
    # 文档解析时，knowledge_id 被嵌入到每个 ChunkModel 中
    chunks = await markdown_parser.parse_into_chunks(file_id, file_path, knowledge_id)
    # 返回的每个 chunk 都包含相同的 knowledge_id
```

**文件**：[markdown.py](src/backend/agentchat/services/rag/doc_parser/markdown.py)

```python
async def parse_into_chunks(self, file_id: str, file_path: str, knowledge_id: str):
    for content in contents:
        chunks.append(ChunkModel(
            chunk_id=chunk_id,
            content=content,
            file_id=file_id,
            file_name=os.path.basename(file_path),
            knowledge_id=knowledge_id,  # ★ 嵌入 knowledge_id
            update_time=update_time.isoformat()
        ))
```

#### 6.2.3 检索时的隔离

**API 入口**：[knowledge.py](src/backend/agentchat/api/v1/knowledge.py)

```python
@router.post("/knowledge/retrieval")
async def retrieval_knowledge(
    query: str,
    knowledge_id: Union[str, List[str]] = Body(...)  # ★ 传入知识库ID
):
    if isinstance(knowledge_id, str):
        content = await RagHandler.retrieve_ranked_documents(
            query, [knowledge_id], [knowledge_id]
        )
    else:
        content = await RagHandler.retrieve_ranked_documents(
            query, knowledge_id, knowledge_id  # ★ 支持多知识库检索
        )
```

**检索入口**：[rag_handler.py](src/backend/agentchat/services/rag_handler.py)

```python
async def mix_retrival_documents(cls, query_list, knowledges_id, search_field):
    # knowledges_id 是知识库ID列表，用于限定检索范围
    es_documents, milvus_documents = await MixRetrival.mix_retrival_documents(
        query_list, knowledges_id, search_field
    )
```

#### 6.2.4 Collection/Index 命名

**ES 索引名**：`knowledge_id` 作为索引名
```python
# es_client.py - 索引创建
if not self.client.indices.exists(index=index_name):
    self.client.indices.create(index=index_name, body=index_config)
```

**Milvus Collection 名**：`knowledge_id` 作为 Collection 名
```python
# milvus_client.py - 集合创建
collection = Collection(collection_name, schema)  # collection_name = knowledge_id
```

**Chroma Collection 名**：`knowledge_id` 作为 Collection 名
```python
# chroma_client.py - 集合创建
collection = self.client.create_collection(
    name=collection_name,  # collection_name = knowledge_id
    metadata={"hnsw:space": "cosine"}
)
```

#### 6.2.5 多知识库检索

当用户绑定多个知识库时，系统支持**跨知识库检索**：

```python
# API 层传入多个 knowledge_id
content = await RagHandler.retrieve_ranked_documents(
    query,
    knowledge_ids,  # List[str]，多个知识库ID
    knowledge_ids   # 同时用于 ES 和 Milvus
)
```

**检索时**：
```python
# MixRetrival.mix_retrival_documents
for query in query_list:
    for knowledge_id in knowledges_id:  # ★ 遍历每个知识库
        es_documents += await cls.retrival_es_documents(query, knowledge_id, ...)
        milvus_documents += await cls.retrival_milvus_documents(query, knowledge_id, ...)
```

---

### 6.3 Memory 系统的用户隔离

#### 6.3.1 多维度过滤机制

Memory 系统使用 **Metadata 过滤**实现细粒度的用户隔离，支持三种标识字段：

```python
def _build_filters_and_metadata(
    user_id: Optional[str] = None,   # ★ 用户ID
    agent_id: Optional[str] = None,  # ★ Agent ID
    run_id: Optional[str] = None,    # ★ Run ID
    actor_id: Optional[str] = None,  # ★ 发言者ID（可选）
):
```

#### 6.3.2 存储时的元数据嵌入

**文件**：[client.py](src/backend/agentchat/services/memory/client.py)

```python
async def _create_memory(self, data, existing_embeddings, metadata=None):
    metadata = metadata or {}
    metadata["data"] = data                    # 记忆内容
    metadata["hash"] = hashlib.md5(data.encode()).hexdigest()
    metadata["created_at"] = datetime.now(pytz.timezone("US/Pacific")).isoformat()
    metadata["user_id"] = user_id              # ★ 嵌入用户ID
    metadata["agent_id"] = agent_id             # ★ 嵌入AgentID
    metadata["run_id"] = run_id                 # ★ 嵌入RunID
    metadata["actor_id"] = actor_id             # ★ 嵌入发言者ID
    metadata["role"] = role                     # ★ 嵌入角色

    await asyncio.to_thread(
        self.vector_store.insert,
        vectors=[embeddings],
        ids=[memory_id],
        payloads=[metadata],
    )
```

#### 6.3.3 检索时的过滤

```python
async def _search_vector_store(self, query, filters, limit, threshold: Optional[float] = None):
    # filters 包含 user_id, agent_id, run_id 等过滤条件
    memories = await asyncio.to_thread(
        self.vector_store.search,
        query=query,
        vectors=embeddings,
        limit=limit,
        filters=filters  # ★ Chroma 的 where 子句过滤
    )
```

**Chroma 中的 where 子句**：

```python
# chroma.py - ChromaDB.search
where_clause = self._generate_where_clause(filters) if filters else None
results = self.collection.query(
    query_embeddings=vectors,
    where=where_clause,  # ★ metadata 过滤
    n_results=limit
)
```

#### 6.3.4 多维度过滤示例

```python
# 场景1：获取用户的所有记忆
memory = await memory_client.get_all(user_id="user_123")

# 场景2：获取用户与特定Agent的对话记忆
memory = await memory_client.get_all(
    user_id="user_123",
    agent_id="agent_456"
)

# 场景3：获取特定Run的所有记忆
memory = await memory_client.get_all(run_id="run_789")

# 场景4：按发言者过滤
memory = await memory_client.search(
    query="关于项目的问题",
    user_id="user_123",
    actor_id="assistant"  # 只搜索助手的回复
)
```

---

### 6.4 两套隔离机制的对比

| 维度 | RAG 隔离 | Memory 隔离 |
|------|----------|-------------|
| **隔离粒度** | 知识库级别 | 会话/消息级别 |
| **实现方式** | Collection/Index 分离 | Metadata 过滤 |
| **查询效率** | 高（物理隔离） | 中（需过滤） |
| **灵活性** | 固定粒度 | 多维度灵活组合 |
| **适用场景** | 文档检索 | 对话历史记忆 |
| **标识字段** | `knowledge_id` | `user_id` + `agent_id` + `run_id` |

---

### 6.5 完整的数据隔离流程图

```
                    ┌─────────────────────────────────────────────────────────┐
                    │                    用户请求入口                         │
                    └─────────────────────────────────────────────────────────┘
                                              │
                          ┌───────────────────┴───────────────────┐
                          │                                       │
                          ▼                                       ▼
          ┌───────────────────────────────┐     ┌───────────────────────────────┐
          │         RAG 系统              │     │       Memory 系统              │
          └───────────────────────────────┘     └───────────────────────────────┘
                          │                                       │
                          ▼                                       ▼
          ┌───────────────────────────────┐     ┌───────────────────────────────┐
          │  knowledge_ids: List[str]     │     │  user_id + agent_id + run_id  │
          └───────────────────────────────┘     └───────────────────────────────┘
                          │                                       │
          ┌───────────────┼───────────────┐           ┌───────────────┼───────────────┐
          │               │               │           │               │               │
          ▼               ▼               ▼           ▼               ▼               ▼
    ┌─────────┐     ┌─────────┐     ┌─────────┐ ┌─────────┐     ┌─────────┐     ┌─────────┐
    │Collection│     │Collection│     │Collection│ │Metadata │     │Metadata │     │Metadata │
    │  KB_1   │     │  KB_2   │     │  KB_3   │ │ user_1 │     │ user_2 │     │ user_3 │
    └─────────┘     └─────────┘     └─────────┘ └─────────┘     └─────────┘     └─────────┘
         (ES Index)     (ES Index)     (ES Index)   (Chroma)      (Chroma)      (Chroma)
```

---

### 6.6 面试题：如何设计多租户向量数据库的隔离方案？

**答案**：

**多租户隔离的常见方案**：

| 方案 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| **Collection 隔离** | 每个租户一个 Collection | 隔离性强，查询高效 | 管理复杂，资源浪费 |
| **Partition 隔离** | 一个 Collection 多个 Partition | 资源利用率高 | 隔离性较弱 |
| **Metadata 过滤** | 所有数据存一个 Collection，按 Metadata 过滤 | 简单灵活 | 查询性能较差 |
| **混合方案** | Collection + Metadata | 平衡隔离与性能 | 实现复杂 |

**项目中的设计**：

1. **RAG 系统采用 Collection 隔离**：
   - 每个 `knowledge_id` 对应一个独立的 Collection/Index
   - 适合知识库场景，隔离性强
   - 查询时直接定位到对应 Collection

2. **Memory 系统采用 Metadata 过滤**：
   - 所有用户记忆存在同一个 Collection
   - 通过 `user_id`、`agent_id`、`run_id` 过滤
   - 适合灵活会话场景

**实际面试追问**：

| 问题 | 考察点 | 答案要点 |
|------|--------|----------|
| Collection 过多怎么办？ | 资源管理 | 使用 Partition 或 Metadata 过滤 |
| Metadata 过滤性能差怎么优化？ | 性能调优 | 建立索引、使用 Partition |
| 跨租户搜索如何实现？ | 架构设计 | 在应用层实现，无跨 Collection 查询 |
| 数据迁移如何处理？ | 运维 | 按 Collection 维度迁移 |

---

## 7. 面试题与答案

### 面试题 1：倒排索引的原理是什么？

**答案**：

倒排索引是搜索引擎的核心数据结构，用于快速全文搜索。

**正向索引（文档 → 词）**：
```
文档1 → ["Elasticsearch", "原理", "索引"]
文档2 → ["倒排索引", "搜索引擎", "原理"]
```

**倒排索引（词 → 文档）**：
```
"Elasticsearch" → [文档1]
"原理" → [文档1, 文档2]
"倒排索引" → [文档2]
"搜索引擎" → [文档2]
"索引" → [文档1]
```

**查询流程**：
1. 用户搜索 "Elasticsearch 原理"
2. 分词器切分查询为 ["Elasticsearch", "原理"]
3. 在倒排索引中查找词项
4. 合并文档列表（交集/并集）
5. 根据相关性算法排序返回

**ES 中的实现**：
- 每个索引包含多个 **Shard（分片）**
- 每个 Shard 包含多个 **Segment**
- 每个 Segment 是独立的倒排索引
- 搜索时遍历所有 Segment，合并结果

---

### 面试题 2：BM25 算法的原理是什么？

**答案**：

BM25（Best Match 25）是 ES 默认的相关性评分算法。

**核心公式**：
```
Score(D, Q) = Σ IDF(qi) × (tf(qi, D) × (k1 + 1)) / (tf(qi, D) + k1 × (1 - b + b × |D|/avgdl))

其中：
- tf(qi, D) = 词项 qi 在文档 D 中的词频
- |D| = 文档长度
- avgdl = 平均文档长度
- k1 = 词频饱和度参数（默认 1.2）
- b = 文档长度归一化参数（默认 0.75）
- IDF(qi) = log((N - n(qi) + 0.5) / (n(qi) + 0.5))
```

**关键特性**：
| 特性 | 说明 |
|------|------|
| 词频饱和 | 词频增加带来的分数增长会逐渐放缓 |
| 文档长度归一化 | 长文档会适当降低分数 |
| IDF 权重 | 常见词（如 "the"）权重低，稀有词权重高 |

**项目中的 boost 配置**：
```json
{
  "match": {
    "content": {
      "boost": 2.0  // 提升 content 字段的权重
    }
  }
}
```

---

### 面试题 3：Milvus 的 IVF_FLAT 索引原理是什么？

**答案**：

**IVF（Inverted File Index）** 是一种高效的向量索引算法。

**原理**：
1. **聚类**：将所有向量用 K-Means 算法聚类为 N 个簇（由 `nlist` 参数控制）
2. **建立倒排索引**：记录每个簇包含哪些向量
3. **搜索**：先找到最近的 K 个簇（`nprobe` 参数），再在簇内精确搜索

**参数说明**：
```python
index_params = {
    "index_type": "IVF_FLAT",
    "metric_type": "L2",      # L2 距离或 IP 内积
    "params": {"nlist": 128}  # 簇的数量
}

search_params = {
    "params": {"nprobe": 16}  # 搜索的簇数量
}
```

**搜索流程**：
```
查询向量
    │
    ▼
┌─────────────────────────────────────┐
│  1. 计算查询向量到所有簇中心的距离     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  2. 找到最近的 nprobe 个簇            │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  3. 在簇内精确搜索最近邻向量          │
└─────────────────────────────────────┘
    │
    ▼
返回 top_k 个结果
```

**IVF_FLAT vs IVF_SQ8**：
- IVF_FLAT：精确检索，不压缩，精度高
- IVF_SQ8：标量量化压缩，内存占用小，可能有精度损失

---

### 面试题 4：HNSW 索引的原理是什么？它和 IVF 有什么区别？

**答案**：

**HNSW（Hierarchical Navigable Small World）** 是一种基于图的近似最近邻搜索算法。

**原理**：
1. **建图**：构建多层图结构，上层稀疏、下层密集
2. **搜索**：从顶层开始贪心搜索，逐层向下精化

**数据结构**：
```
Layer 2:  [A] ────── [B]         （稀疏，远程跳转）
            │         │
Layer 1:  [A] ── [C] ── [D]     （中等密度）
            │     │     │
Layer 0:  [A] ── [C] ── [D] ── [E]  （密集，最近邻）
```

**参数**：
```python
# Chroma 中的 HNSW 配置
collection = client.create_collection(
    name=collection_name,
    metadata={"hnsw:space": "cosine"}  # cosine/L2/ip
)
```

| 对比项 | HNSW | IVF |
|--------|------|-----|
| 原理 | 分层图搜索 | 聚类 + 倒排索引 |
| 搜索速度 | 快 | 中等 |
| 内存占用 | 高 | 中等 |
| 建图速度 | 慢 | 快 |
| 适用场景 | 追求高精度 | 内存受限场景 |

**Chroma 默认使用 HNSW**，因为它是纯 Python 实现，部署简单。

---

### 面试题 5：余弦相似度和 L2 距离有什么区别？

**答案**：

**L2 距离（欧氏距离）**：
```
d = √(Σ(a_i - b_i)²)
```
- 衡量向量间的绝对距离
- 值越小越相似

**余弦相似度**：
```
cos(θ) = (A · B) / (|A| × |B|)
```
- 衡量向量间的方向夹角
- 值越大越相似（1 表示完全相同）

**距离转换**：
```python
# Chroma 返回的是 distance，需要转换为 similarity
score = 1.0 - distance  # 适用于 L2 和 cosine

# 如果是余弦距离本身就是相似度
```

**项目中的使用**：
- **Milvus**：`metric_type: "L2"`（L2 距离）
- **Chroma**：`hnsw:space: "cosine"`（余弦相似度）

---

### 面试题 6：向量数据库如何实现高可用？

**答案**：

**Milvus 高可用方案**：

1. **集群模式**：
   - Milvus Cluster：分布式部署，多节点协作
   - etcd 协调服务
   - MinIO/S3 对象存储

2. **数据复制**：
```yaml
# Milvus 集群配置
etcd:
  endpoints:
    - etcd:2379

storage:
  type: minio
  minio:
    server: minio:9000
```

3. **故障转移**：
   - 当主节点故障时，备节点自动升级
   - 查询负载均衡到多个只读节点

**Chroma 高可用方案**：
- Chroma 目前主要定位为轻量级向量库
- 生产环境建议使用 Milvus、Pinecone 等企业级方案
- 可通过多实例 + 负载均衡实现简单高可用

---

### 面试题 7：什么是向量嵌入（Embedding）？项目中如何生成？

**答案**：

**向量嵌入**是将文本转换为稠密向量的技术，语义相似的文本在向量空间中距离更近。

**项目中的嵌入生成**：

**文件**：[embedding.py](src/backend/agentchat/services/rag/embedding.py)

```python
async def get_embedding(texts: List[str]) -> List[List[float]]:
    # 使用配置的嵌入模型生成向量
    embedding_model = ModelManager.get_embedding_model()
    embeddings = await embedding_model.embed(texts)
    return embeddings
```

**使用场景**：
```python
# Milvus 中生成内容向量 + 摘要向量
embedding_list = await get_embedding(content_list)           # 内容向量
embedding_summary_list = await get_embedding(summary_list)  # 摘要向量

# Chroma 中同样使用嵌入
all_embeddings = await get_embedding(documents)
```

---

### 面试题 8：Chroma 的 `where` 过滤条件如何使用？

**答案**：

**Chroma 的 where 子句**：

```python
# 单条件过滤
results = collection.query(
    query_embeddings=[query_embedding],
    where={"is_summary": True},  # 只查询 is_summary=True 的文档
    n_results=10
)

# 多条件 AND
where_clause = {"$and": [
    {"file_id": "xxx"},
    {"knowledge_id": "yyy"}
]}
```

**项目中的应用**：

```python
# RAG 查询时过滤摘要条目（chroma_client.py）
for i in range(len(results['ids'][0])):
    metadata = results['metadatas'][0][i]
    if metadata.get("is_summary", False):
        continue  # 跳过摘要，只返回原始内容
```

**与 Milvus 的对比**：

| 特性 | Chroma where | Milvus expr |
|------|--------------|-------------|
| 语法 | `{"field": value}` | `field == "value"` |
| 多条件 | `{"$and": [...]}` | `field1 == "x" && field2 == "y"` |
| 性能 | 内存过滤 | 服务端过滤 |

---

### 面试题 9：Milvus 的 `search_params` 中 `nprobe` 参数如何调优？

**答案**：

**nprobe** 决定了搜索时检查的簇数量，影响精度和性能的平衡。

**调优原则**：
- `nprobe` ↑ = 精度 ↑ = 性能 ↓
- `nprobe` ↓ = 精度 ↓ = 性能 ↑

**经验公式**：
```
nprobe = nlist × recall_rate
其中 nlist 是建索引时的簇数
```

**示例**：
```python
# 项目配置
index_params = {"nlist": 128}    # 建索引时
search_params = {"nprobe": 16}  # 搜索时（128的1/8）

# 如果需要更高精度
search_params = {"nprobe": 64}  # 检查更多簇
```

**性能对比**：
| nprobe | 搜索精度 | 搜索时间 |
|--------|----------|----------|
| 8 | ~80% | 快速 |
| 16 | ~90% | 中等 |
| 32 | ~95% | 较慢 |
| 64 | ~98% | 慢 |

---

### 面试题 10：RAG 中的混合检索是什么？为什么需要混合检索？

**答案**：

**混合检索**结合多种检索方法，弥补单一检索的不足。

**项目实现**：
```python
class MixRetrival:
    @classmethod
    async def mix_retrival_documents(cls, query_list, knowledges_id, search_field):
        es_documents = []   # ES 关键词检索结果
        milvus_documents = []  # Milvus 向量检索结果

        for query in query_list:
            # 并行执行两种检索
            es_documents += await cls.retrival_es_documents(...)
            milvus_documents += await cls.retrival_milvus_documents(...)
```

**为什么需要混合检索**：

| 检索方式 | 优势 | 劣势 |
|----------|------|------|
| **ES 关键词** | 精确匹配、模糊匹配、拼写纠错 | 无法理解语义 |
| **向量检索** | 语义相似度匹配 | 对关键词精确匹配不敏感 |

**合并策略**：
```python
# 1. 各自排序
es_documents.sort(key=lambda x: x.score, reverse=True)
milvus_documents.sort(key=lambda x: x.score, reverse=True)

# 2. 合并去重，保留最高分
seen_chunk_ids = set()
for doc in all_documents:
    if doc.chunk_id not in seen_chunk_ids:
        documents.append(doc)
```

---

### 面试题 11：Chroma 和 Milvus 的区别是什么？如何选型？

**答案**：

| 对比项 | Chroma | Milvus |
|--------|--------|--------|
| 部署复杂度 | 简单（pip install） | 中等（需要启动服务） |
| 数据规模 | 百万级 | 十亿级 |
| 索引类型 | HNSW | IVF_FLAT、IVF_SQ8、HNSW 等 |
| 分布式支持 | 有限 | 成熟 |
| 查询性能 | 中等 | 高 |
| 内存占用 | 较高 | 可优化 |

**项目中的选择**：

```python
# vector_db/__init__.py
if app_settings.rag.vector_db.get("mode") == "chroma":
    milvus_client = ChromaClient()      # 轻量级部署
elif app_settings.rag.vector_db.get("mode") == "lite":
    milvus_client = MilvusLiteClient()  # 单机 Milvus
else:
    milvus_client = MilvusClient()      # 分布式 Milvus
```

**选型建议**：
- **小规模（<100万向量）**：Chroma，部署简单
- **中等规模（100万-1亿）**：Milvus 单机
- **大规模（>1亿）**：Milvus 分布式集群

---

### 面试题 12：ES 的分片机制是什么？为什么需要副本？

**答案**：

**分片（Shard）**：
- 将索引水平拆分，每个分片是一个独立的 Lucene 索引
- 默认 5 个主分片（创建索引时指定）
- 分片数固定后不宜修改

**副本（Replica）**：
- 主分片的拷贝，提供数据冗余
- 默认 1 个副本
- 副本分片可接受查询，分担压力

**数据写入流程**：
```
客户端请求
    │
    ▼
协调节点（任意节点）
    │
    ▼
转发到主分片所在节点
    │
    ▼
主分片写入 ──────→ 并行写入副本分片
    │
    ▼
返回客户端
```

**项目配置**：
```yaml
elasticsearch:
  hosts: "http://127.0.0.1:9200"  # 单节点，无副本
```

**生产环境建议**：
```yaml
index:
  number_of_shards: 3
  number_of_replicas: 2  # 2 副本保证高可用
```

---

### 面试题 13：Memory 系统中 Chroma 的作用是什么？

**答案**：

**Memory 系统架构**：

```
用户对话
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  AsyncMemory                                                │
│  ├── _add_to_vector_store() → ChromaDB 存储记忆向量          │
│  └── _add_to_graph() → 图数据库（暂未启用）                  │
└─────────────────────────────────────────────────────────────┘
```

**记忆类型**：
```python
class MemoryType(Enum):
    SEMANTIC = "semantic_memory"      # 语义记忆
    EPISODIC = "episodic_memory"      # 情景记忆
    PROCEDURAL = "procedural_memory"  # 程序记忆
```

**添加记忆流程**：
```python
async def _add_to_vector_store(self, messages, metadata, effective_filters, infer):
    for message_dict in messages:
        msg_embeddings = await asyncio.to_thread(
            self.embedding_model.embed, msg_content
        )
        mem_id = await self._create_memory(
            msg_content, msg_embeddings, per_msg_meta
        )
```

**检索记忆**：
```python
async def _search_vector_store(self, query, filters, limit, threshold):
    embeddings = await asyncio.to_thread(self.embedding_model.embed, query)
    memories = await asyncio.to_thread(
        self.vector_store.search,
        query=query,
        vectors=embeddings,
        limit=limit,
        filters=filters  # user_id, agent_id, run_id 过滤
    )
```

---

### 面试题 14：ES 的 `match` 查询和 `term` 查询区别？

**答案**：

| 查询类型 | 分词 | 适用字段 | 场景 |
|----------|------|----------|------|
| `term` | 不分词，精确匹配 | keyword、数值、布尔 | 精确值筛选 |
| `match` | 分词后匹配 | text | 全文搜索 |

**项目代码**：

```python
# term 查询 - 精确匹配 file_id
{
    "query": {
        "term": {
            "file_id": "doc_123"  # 精确匹配
        }
    }
}

# match 查询 - 分词后匹配 content
{
    "query": {
        "match": {
            "content": {
                "query": "机器学习算法",
                "analyzer": "ik_smart",
                "operator": "and"  # 所有分词都要匹配
            }
        }
    }
}
```

**为什么 content 用 match？**
- content 是 text 类型，经过 IK 分词
- 搜索 "机器学习" 会先被分词为 ["机器", "学习"]
- term 查询无法匹配分词后的结果

---

### 面试题 15：向量检索中的 `top_k` 和 `min_score` 如何设置？

**答案**：

**top_k**：返回的最相似结果数量

```python
# 项目中的 top_k 配置
top_k = app_settings.rag.retrival.get('top_k')  # 默认 5
```

**min_score**：结果的最低相似度阈值

```python
# 项目中的 min_score 配置
min_score = app_settings.rag.retrival.get('min_score')  # 默认 0.2
```

**过滤逻辑**：
```python
for doc in reranked_docs[:top_k]:
    if doc.score >= min_score:
        filtered_results.append(doc)
```

**调优建议**：

| 场景 | top_k | min_score | 说明 |
|------|-------|-----------|------|
| 精确场景 | 3-5 | 0.5-0.7 | 减少召回，提高精度 |
| 宽松场景 | 10-20 | 0.2-0.3 | 增加召回，可能降低精度 |
| 平衡 | 5-10 | 0.3-0.5 | 常用推荐值 |

---

### 面试题 16：Chroma 的 PersistentClient 如何工作？

**答案**：

**持久化客户端**：
```python
class ChromaClient:
    def _connect(self):
        self.client = chromadb.PersistentClient(path="./vector_db")
```

**工作原理**：
1. 首次连接时，在指定路径创建 SQLite 数据库
2. 所有增删改操作自动持久化到磁盘
3. 下次启动时自动加载已有数据

**数据存储结构**：
```
vector_db/
├── chroma.sqlite3          # SQLite 数据库文件
├── 00000000-0000-0000-...  # 向量数据文件
└── ...
```

**持久化 vs 内存客户端**：
```python
# 内存客户端（不持久化）
client = chromadb.Client()  # 数据在内存，进程退出即丢失

# 持久化客户端
client = chromadb.PersistentClient(path="./vector_db")  # 数据持久化到磁盘
```

---

### 面试题 17：Milvus 的 Collection 和 Partition 是什么关系？

**答案**：

**Collection（集合）**：
- 类似于表，是向量的顶层容器
- 可创建索引和搜索
- 每个 Collection 有独立的 schema

**Partition（分区）**：
- Collection 的逻辑分区
- 可独立加载/释放
- 用于优化大规模数据的管理

**项目中的使用**：
```python
# MilvusClient 中按 knowledge_id 区分集合
collection_name = knowledge_id  # 每个知识库一个 Collection

# ChromaClient 中类似
collection_name = knowledge_id
```

**Partition 适用场景**：
- 数据有时间属性，按时间分区
- 多租户场景，按租户分区
- 冷热数据分离

---

### 面试题 18：向量数据库的召回率和精确率如何平衡？

**答案**：

**召回率 vs 精确率**：
- **召回率**：相关文档被检索出来的比例
- **精确率**：检索结果中相关文档的比例

**近似最近邻（ANN）的trade-off**：
```
召回率 ↑ ←→ 精确率 ↓ ←→ 性能 ↓ ←→ 搜索时间 ↑
```

**调优方法**：

| 参数 | 调高效果 | 调低效果 |
|------|----------|----------|
| `nprobe` (IVF) | 召回率↑ | 召回率↓ |
| `ef` (HNSW) | 召回率↑ | 召回率↓ |
| `top_k` | 召回率↑ | 可能降低精确率 |

**项目配置**：
```python
# Milvus - 平衡配置
search_params = {
    "metric_type": "L2",
    "params": {"nprobe": 16}  # 适中
}

# Chroma - HNSW 参数
metadata = {"hnsw:space": "cosine"}  # 使用默认 HNSW 参数
```

---

### 面试题 19：ES 的 Analysis（分析器）机制是什么？

**答案**：

**Analyzer 组成**：
```
字符过滤器（Character Filters）
    ↓
分词器（Tokenizer）
    ↓
词项过滤器（Token Filters）
```

**ES 内置分词器**：

| 分词器 | 行为 |
|--------|------|
| `standard` | 按单词边界切分，小写化 |
| `simple` | 按非字母字符切分，小写化 |
| `whitespace` | 按空格切分 |
| `keyword` | 不分词 |

**IK 中文分词器**：
```json
{
  "settings": {
    "analysis": {
      "analyzer": {
        "ik_analyzer": {
          "type": "custom",
          "tokenizer": "ik_smart"
        }
      }
    }
  }
}
```

**分词示例**：
```
输入: "机器学习是人工智能的分支"

ik_smart: ["机器学习", "是", "人工智能", "的", "分支"]
ik_max_word: ["机器", "学习", "机器学习", "是", "人工", "智能", "人工智能", ...]
```

**项目配置**：
```python
# es_index.py 中定义
"content": {
    "type": "text",
    "analyzer": "ik_analyzer"  # 使用 IK 分词
}
```

---

### 面试题 20：如何理解 RAG 中的查询重写（Query Rewrite）？

**答案**：

**查询重写目的**：
- 用户 query 可能表达不清
- 同一语义有多种表达方式
- 扩展查询，覆盖更多相关文档

**项目实现**：
```python
class RagHandler:
    @classmethod
    async def query_rewrite(cls, query):
        rewritten_queries = await query_rewriter.rewrite(query)
        return rewritten_queries
```

**使用方式**：
```python
# rag_handler.py
if needs_query_rewrite:
    rewritten_queries = await cls.query_rewrite(query)
else:
    rewritten_queries = [query]

# 对每个重写后的查询分别检索
for query in rewritten_queries:
    es_documents += await cls.retrival_es_documents(query, ...)
    milvus_documents += await cls.retrival_milvus_documents(query, ...)
```

**重写策略**：
1. **同义词扩展**：输入 → ["输入", "录入", "键入"]
2. **语义扩展**：输入 → ["输入", "input", "数据录入"]
3. **多语言**：输入 → ["输入", "input", "インプット"]

---

## 附录：关键代码路径

| 文件 | 作用 |
|------|------|
| [es_client.py](src/backend/agentchat/services/rag/es_client.py) | ES 客户端 |
| [es_index.py](src/backend/agentchat/config/es_index.py) | ES 索引配置 |
| [milvus_client.py](src/backend/agentchat/services/rag/vector_db/milvus_client.py) | Milvus 客户端 |
| [milvus_lite_client.py](src/backend/agentchat/services/rag/vector_db/milvus_lite_client.py) | 轻量 Milvus |
| [chroma_client.py](src/backend/agentchat/services/rag/vector_db/chroma_client.py) | RAG Chroma 客户端 |
| [chroma.py](src/backend/agentchat/services/memory/vector_stores/chroma.py) | Memory Chroma |
| [rag_handler.py](src/backend/agentchat/services/rag_handler.py) | RAG 流程处理 |
| [retrieval.py](src/backend/agentchat/services/retrieval.py) | 混合检索实现 |
| [client.py](src/backend/agentchat/services/memory/client.py) | Memory 服务 |
| [config.yaml](src/backend/agentchat/config.yaml) | 配置文件 |
