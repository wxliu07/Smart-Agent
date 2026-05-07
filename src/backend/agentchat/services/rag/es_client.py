import json
from typing import List
from elasticsearch import Elasticsearch

from agentchat.config.es_index import ESIndex
from agentchat.schema.chunk import ChunkModel
from agentchat.schema.search import SearchModel
from agentchat.settings import app_settings
from loguru import logger


class ESClient:
    """
    Elasticsearch 客户端封装类，提供文档的增删改查功能。
    用于将文本块（chunks）索引到 Elasticsearch 中，并支持基于内容和摘要的搜索。
    """

    def __init__(self):
        """
        初始化 ESClient 实例。
        从应用配置中获取 Elasticsearch 的主机地址，并创建 Elasticsearch 客户端连接。
        """
        # 从应用配置中获取 Elasticsearch 主机地址，并初始化客户端
        self.client = Elasticsearch(hosts=app_settings.rag.elasticsearch.get('hosts'))

    async def insert_documents(self, index_name, chunks: List[ChunkModel]):
        """
        将文档块插入到指定的 Elasticsearch 索引中。
        如果索引不存在，则根据配置创建索引。

        Args:
            index_name: Elasticsearch 索引名称
            chunks: 要插入的文档块列表，每个元素为 ChunkModel 类型

        Raises:
            ValueError: 当索引创建失败时抛出异常
        """
        # 加载索引配置（映射和分析器等设置）
        index_config = json.loads(ESIndex.index_config)

        # 检查索引是否存在，如果不存在则创建
        if not self.client.indices.exists(index=index_name):
            try:
                # 使用预定义的配置创建索引cls
                self.client.indices.create(index=index_name, body=index_config)
                logger.info(f'index name: {index_name} 创建成功')
            except Exception as e:
                logger.error(f"index name {index_name} error: {e}")
                raise ValueError(f"index create error")

        try:
            # 遍历所有文档块并索引到 Elasticsearch 中
            for chunk in chunks:
                self.client.index(
                    index=index_name,
                    body=chunk.to_dict()  # 将 ChunkModel 对象转换为字典
                )
                logger.info(f'chunk id: {chunk.chunk_id} 已存到索引中')
        except Exception as e:
            logger.error(f"索引增加数据失败：{e}")
        finally:
            # 关闭客户端连接
            await self.close()

    async def index_documents(self, index_name, chunks):
        """
        insert_documents 方法的别名，提供更语义化的方法名。

        Args:
            index_name: Elasticsearch 索引名称
            chunks: 要索引的文档块列表
        """
        await self.insert_documents(index_name, chunks)

    async def search_documents(self, query, index_name):
        """
        根据查询文本在指定索引中搜索文档（基于内容字段）。

        Args:
            query: 搜索查询文本
            index_name: 要搜索的索引名称

        Returns:
            List[SearchModel]: 搜索结果列表，每个元素包含文档的分数和详细信息
        """
        # 构建搜索查询，使用预定义的 index_search_content 模板
        index_search = json.loads(ESIndex.index_search_content.format(query=query))

        documents = []
        try:
            # 执行搜索请求
            response = self.client.search(index=index_name, body=index_search)
            hits = response['hits']

            # 如果没有匹配结果（max_score 为 None），返回空列表
            if not hits.get("max_score"):
                return documents

            # 遍历搜索结果，构建 SearchModel 对象列表
            for hit in response['hits']:
                documents.append(SearchModel(
                    score=hit['_score'],  # 搜索相关性分数
                    chunk_id=hit['_source']['chunk_id'],  # 文档块ID
                    update_time=hit['_source']['update_time'],  # 更新时间
                    content=hit['_source']['content'],  # 文档内容
                    file_name=hit['_source']['file_name'],  # 文件名
                    summary=hit['_source']['summary'],  # 文档摘要
                    file_id=hit['_source']['file_id'],  # 文件ID
                    knowledge_id=hit['_source']['knowledge_id']  # 知识库ID
                ))
        except Exception as e:
            logger.error(f'Search documents error: {e}')
        finally:
            await self.close()
            return documents

    async def search_documents_summary(self, query, index_name):
        """
        根据查询文本在指定索引中搜索文档（基于摘要字段）。

        Args:
            query: 搜索查询文本
            index_name: 要搜索的索引名称

        Returns:
            List[SearchModel]: 搜索结果列表，每个元素包含文档的分数和详细信息
        """
        # 构建基于摘要的搜索查询
        index_search = json.loads(ESIndex.index_search_summary.format(query=query))

        documents = []
        try:
            # 执行搜索请求
            response = self.client.search(index=index_name, body=index_search)

            # 遍历搜索结果，构建 SearchModel 对象列表
            for hit in response['hits']:
                documents.append(SearchModel(
                    score=hit['_score'],  # 搜索相关性分数
                    chunk_id=hit['_source']['chunk_id'],  # 文档块ID
                    update_time=hit['_source']['update_time'],  # 更新时间
                    content=hit['_source']['content'],  # 文档内容
                    file_name=hit['_source']['file_name'],  # 文件名
                    summary=hit['_source']['summary'],  # 文档摘要
                    file_id=hit['_source']['file_id'],  # 文件ID
                    knowledge_id=hit['_source']['knowledge_id']  # 知识库ID
                ))

        except Exception as e:
            logger.error(f'Search documents summary error: {e}')
        finally:
            await self.close()
            return documents

    async def delete_documents(self, file_id, index_name):
        """
        根据文件ID删除指定索引中的相关文档。

        Args:
            file_id: 文件ID，用于标识要删除的文档
            index_name: Elasticsearch 索引名称
        """
        try:
            # 构建删除查询条件，根据 file_id 匹配文档
            delete_query = json.loads(ESIndex.index_delete.format(file_id=file_id))

            # 执行批量删除操作
            self.client.delete_by_query(index=index_name, body=delete_query)
            logger.info(f'Success delete documents in file id: {file_id}')
        except Exception as e:
            logger.error(f'Delete documents Error: {e}')

    async def close(self):
        """
        关闭 Elasticsearch 客户端连接。
        当前方法为占位符，实际连接关闭逻辑可根据需要实现。
        """
        pass


# 创建全局 Elasticsearch 客户端实例
client = ESClient()
