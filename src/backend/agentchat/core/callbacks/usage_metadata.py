import threading
from typing import Any
from loguru import logger
from typing_extensions import override  # 标记重写的方法

from langchain_core.callbacks import BaseCallbackHandler    # langchain_core 回调处理器基
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata, add_usage
from langchain_core.outputs import ChatGeneration, LLMResult

from agentchat.api.services.usage_stats import UsageStatsService    # 记录和同步 Token 用量
from agentchat.utils.contexts import get_user_id_context, get_agent_name_context


class UsageMetadataCallbackHandler(BaseCallbackHandler):
    """
    回调处理器：跟踪 AIMessage 中的 Token 用量元数据（usage_metadata）
    核心功能：
    1. 监听 LLM 调用结束事件，提取 Token 用量
    2. 按模型名称汇总 Token 用量
    3. 将用量数据同步到统计服务
    """

    def __init__(self) -> None:
        """Initialize the UsageMetadataCallbackHandler."""
        super().__init__()
        self._lock = threading.Lock()   # 线程锁，保证多线程环境下修改共享数据时的线程安全
        self.usage_metadata: dict[str, UsageMetadata] = {}  # 存储按模型名称分类的 Token 用量元数据，key=模型名称，value=UsageMetadata 对象

    @override
    def __repr__(self) -> str:
        """自定义实例的字符串表示形式，返回当前记录的 Token 用量元数据"""
        return str(self.usage_metadata)

    @override
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """
        LLM 调用结束时触发的回调方法：收集并汇总 Token 用量
        Args:
            response: LLMResult 对象，包含 LLM 调用的结果（生成的消息、用量等）
            **kwargs: 其他可选参数"""
        # Check for usage_metadata (langchain-core >= 0.2.2)

        try:
            generation = response.generations[0][0]
        except IndexError:
            generation = None

        usage_metadata = None
        model_name = None
        if isinstance(generation, ChatGeneration):  # 检查类型，并获取 usage_metadata 和模型名称
            try:
                message = generation.message
                if isinstance(message, AIMessage):
                    usage_metadata = message.usage_metadata
                    model_name = message.response_metadata.get("model_name")
            except AttributeError:
                pass

        # update shared state behind lock
        if usage_metadata and model_name:
            # 使用线程锁保证多线程下修改共享字典的安全性
            with self._lock:
                # 如果模型名称未在字典中，直接添加
                if model_name not in self.usage_metadata:
                    self.usage_metadata[model_name] = usage_metadata
                else:
                    # 如果模型已存在，累加 Token 用量（调用 add_usage 合并两个 UsageMetadata）
                    self.usage_metadata[model_name] = add_usage(
                        self.usage_metadata[model_name], usage_metadata
                    )
                self.record_token_usage(model_name, usage_metadata)

    def record_token_usage(self, model_name, usage_metadata):
        """
        记录 Token 用量并同步到用量统计服务
        Args:
            model_name: 模型名称
            usage_metadata: Token 用量元数据对象
        """
        user_id = get_user_id_context()  # 从上下文获取当前请求的用户 ID
        agent_name = get_agent_name_context()   # 从上下文获取当前使用的代理名称

        record = {
            'model': model_name,
            "agent": agent_name,
            "user_id": user_id,
            'input_tokens': usage_metadata.get("input_tokens", 0),
            'output_tokens': usage_metadata.get("output_tokens", 0),
        }
        logger.info(f"{model_name} cost input tokens: {usage_metadata.get("input_tokens")}, output tokens: {usage_metadata.get("output_tokens")}")

        # 调用用量统计服务的同步方法，将记录写入数据库/服务
        UsageStatsService.sync_create_usage_stats(**record)
