# LLM 多 Provider 架构

## 设计原则

每个 LLM API 调用分解为四个**独立**维度，每个维度可独立替换：

```
LLMRequest → Route → HTTP Request → HTTP Client → Framing → Protocol → Stream<StreamEvent>
```

---

## 四维规格

### Protocol — 语义协议

Provider 的语义 API 约定。不关心 URL、认证方式、字节传输，只关心：

- 请求体的结构
- 如何解析流式响应

**只有这里知道 Provider 原生字段**，原生字段到内部通用 `StreamEvent` 的转换也在此发生。

### Endpoint — 端点构造

只关心 URL 构造，解决请求发送到什么地方的问题。

### Auth — 认证

只关心如何注入认证凭据。

### Framing — 字节帧转换

只关心字节流到结构化帧的转换。

---

## Route — 组合器

组合四个维度完成全程访问：

1. Endpoint 构造 URL
2. Protocol 构建请求体
3. Auth 注入认证
4. HTTP Client 发送请求
5. Framing 将字节流解析为帧
6. Protocol 将帧翻译为内部事件

---

## 数据流

```
LLMRequest → Route
  ├─ Endpoint → URL
  ├─ Protocol → body dict
  ├─ Auth → headers
  ▼
HTTP Client（重试、错误映射）
  ▼
Framing（字节流 → dict 帧）
  ▼
Protocol（原生字段 → StreamEvent）
  ▼
Stream<StreamEvent> → Agent Loop
```

---

## 文件组织

```
llm/
├── __init__.py            # 空
├── README.md              # 本文档
│
├── specs/                 # 【公开】四维接口定义（仅 ABC）
│   ├── protocol.py
│   ├── endpoint.py
│   ├── auth.py
│   └── framing.py
│
├── protocols/             # 【公开】Protocol 实现
│   ├── openai.py          # OpenAIProtocol, OpenAIEndpoint
│   └── deepseek.py        # DeepseekProtocol
│
├── facade.py              # 【公开】LLM 门面类
├── builders.py            # 【公开】便捷 Route 构建器
│
├── _route.py              # 【内部】Route + HTTPClient
├── _bearer_auth.py        # 【内部】BearerAuth
└── _sse_framing.py        # 【内部】SSEFraming
```

---

## Schemas

项目级别通用模型定义在 `laffyhand/agent/schemas.py`，包括 `LLMRequest`、各类 `Message`、`StreamEvent`、`ToolDefinition`、`Usage` 等。

**Provider-specific 原始字段模型仅在 `protocols/` 中定义**，不会泄露到外部。

---

## 添加新 Provider

1. 在 `protocols/` 中实现 `Protocol` 子类
2. 可选实现 `Endpoint` 子类
3. 在 `builders.py` 中添加便捷构建函数
