---
agent_id: "search"
label: "light_file_conversion"
version: "1.0.0"
---
用户输入：
“把这个 pdf 转成 word 文档发给我。”

期望行为：

- 识别为轻量文件处理请求。
- 如果运行时支持 pdf_to_docx，就在轻闭环中完成。
- 如果缺少附件或运行时不可用，要明确指出，不假装成功。

示例输出：

```json
{
  "mode": "light_closed_loop",
  "action": "pdf_to_docx",
  "status": "completed_or_failed_truthfully",
  "handoff_summary": "已尝试通过轻执行运行时处理 PDF 转 Word。"
}
```
