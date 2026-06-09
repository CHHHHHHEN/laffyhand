# Message: 组成 Session 的基本部分

## 字段设计

| 字段名 | 字段类型 | 备注 |
|--------|---------|---------|
| `id` | `TEXT` | 唯一消息 ID (主键) |
| `session_id` | `TEXT` | 所属会话 ID,外键关联 `session(id)`,级联删除 |
| `type` | `TEXT` | 消息类型:`user` / `assistant` / `synthetic` / `shell` / `agent-switched` / `model-switched` / `compaction` |
| `time_created` | `INTEGER` | 创建时间,Unix 毫秒时间戳 |
| `time_updated` | `INTEGER` | 更新时间,Unix 毫秒时间戳 |
| `data` | `TEXT` | JSON 格式的多态数据载荷,内容随 `type` 变化 |


## 不同 type 的 data 结构

### `user`

存储用户发送给 Assistant 的消息内容

```json
{
  "text": "用户输入的消息内容",
  "files": [
    { "path": "用户通过 @ 内联到消息中的文件路径", "content": "该文件对应的文件内容"}
    ],
  "agents": [
    "用户主动 @ 的 Agent 名称"
    ],
  "references": [
    "用户通过 @ 指定的参考文件夹路径"
    ]
}
```

### `assistant`

存储 Assistant 回复的消息

```json
{
  "agent": "产生当前消息的 Agent 名称",
  "model": {
    "id": "生成本条消息的模型 ID",
    "provider": "生成本条消息的模型所属的提供商 ID",
    "variant": "模型回复时所处的思考深度等级, 可选 none|low|medium|high|xhigh"
    },
  "content": [ # content 中可以包含多个 text/reasoning/tool 块, 按照时间顺序排列
    { "type": "text", "text": "本条消息文本内容" },
    { "type": "reasoning", "id": "推理块 ID", "text": "本条消息推理内容" },
    {
      "type": "tool",
      "id": "工具调用 ID",
      "name": "工具名称",
      "state": {
        "status": "pending|running|completed|error",
        "input": {},
        "structured": null,
        "content": [],
        "error": ""
      },
      "time": {
        "created": 0,
        "completed": null
        }
    }
  ],
  "finish": "stop",
  "tokens": {
    "input": 0,
    "output": 0,
    "reasoning": 0,
    "cache": {
        "read": 0,
        "write": 0
        }
    },
  "error": null
}
```

### `synthetic`

```json
{
  "session_id": "源会话 ID",
  "text": "系统插入的合成消息文本"
}
```

### `shell`

```json
{
  "callID": "调用 ID",
  "command": "执行的命令",
  "output": "命令输出",
  "truncated": false,
  "is_error": false,
  "time": { "created": 0, "completed": 0 }
}
```

### `agent-switched`

```json
{
  "agent": "切换到的 Agent 名称"
}
```

### `model-switched`

```json
{
  "model": { "id": "模型 ID", "provider": "提供商 ID", "variant": "none|low|medium|high|xhigh" }
}
```

### `compaction`

```json
{
  "reason": "压缩原因",
  "summary": "压缩摘要",
  "include": null
}
```
