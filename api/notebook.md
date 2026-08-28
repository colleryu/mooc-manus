**MCP服务配置
1.将所有mcp_server_config存储到config.yaml文件中
2.从config.yaml中读取数据转换为json
3.将json传递给mcp client manager（MCP客户端管理器）
4.初始化mcp服务器的链接，同时获取对应的工具列表进行缓存
5.当更新数据或者定时事件到了之后才清楚缓存
6.获取MCP服务器 + 工具列表接口、启用/禁用MCP工具、删除MCP服务、新增MCP服务



**A2A服务配置
1.get_agent_cards():获取所有智能体卡片信息，Agent名字、描述、id、同时将方法配置成BaseTool,绑定到执行Agent上
2.执行Agent觉得需要调用Agent时，会调用另外工具
3.call_a2a_agent(id,task)执行agent觉得需要调用a2a agent时，会将agent的id + task任务传递给call_a2a_agent
4.jsonrpc 数据模块，同时传递message给对应的agent端点