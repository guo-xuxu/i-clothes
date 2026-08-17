"""Repository 抽象基类：数据访问层的统一契约。

设计约定：
- 每个数据源一个 Repository 实现：LLM 模型（model_repo）、
  关系型数据库（user 等）、向量库、知识图谱。
- 业务层（services/）只依赖本抽象，不依赖具体数据源，
  新数据源接入 = 新增一个实现 + 在 service 注入，接口层与工作流无需改动。
- 当前作为契约标记，具体方法随各数据源落地时补充。
"""
from abc import ABC


class Repository(ABC):
    """所有数据访问实现的基类。"""
