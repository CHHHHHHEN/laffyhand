每个工具调用结果统一使用 <ToolContent> </ToolContent> 进行包裹，若工具调用被打断/出错/超时，需要在XML标签中进行标注，如 <ToolContent> Tool Execute Timeout after 120s </ToolContent>。

工具并行调用通过 asyncio.gather 实现。

工具需要划分为可并发和不可并发两种类型，对于可并发执行工具（如纯读取）使用 asyncio.gather 并发运行；对于不可并发执行（同时写同一个文件）需要顺序执行。

工具需要进行危险检测，包含危险路径匹配，危险指令匹配。
