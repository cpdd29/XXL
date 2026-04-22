---
agent_id: "search"
label: "light_file_summary"
version: "1.0.0"
---
用户输入：
“把这个 PDF 快速提炼三点给我，不用写成正式邮件。”

期望行为：

- 识别为轻量文件处理请求，前提是文件已提供或存在明确可读引用。
- 使用 `pdf_read` / `pdf_summary` 完成只读摘要，不扩展成写作派工。
- 如果缺少文件输入，应先指出缺口，而不是假装已经处理。

示例输出：

```json
{
  "result_type": "light_file_result",
  "tool_chain": [
    "pdf_read",
    "pdf_summary"
  ],
  "summary": "文档主要讲三点：目标范围、上线步骤、回滚要求。",
  "requires_file": true,
  "upgrade_to_professional_workflow": false
}
```
