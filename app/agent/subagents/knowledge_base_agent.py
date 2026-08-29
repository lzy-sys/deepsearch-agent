"""
知识库子智能体配置模块

将 app/prompt/prompts.yml 中的 rag 配置与自研 RAG 工具组装成
DeepAgents 可识别的字典式子智能体。主智能体后续会根据 description
决定是否把企业内部非结构化文档查询任务分派给它。
"""

from app.agent.prompts import sub_agents_content
from app.tools.rag_tools import ask_knowledge_base, list_knowledge_bases

# 知识库子智能体处理内部非结构化文档，与网络搜索助手、数据库查询助手形成互补
# 它遵循“先列出知识库 -> 再向匹配知识库提问”的工作顺序
# tools 列表声明该子智能体可以发现知识库，并基于检索结果回答问题
knowledge_base_agent = {
    "name": sub_agents_content["rag"]["name"],
    "description": sub_agents_content["rag"]["description"],
    "system_prompt": sub_agents_content["rag"]["system_prompt"],
    "tools": [list_knowledge_bases, ask_knowledge_base],
}
