# reception/security_monitor

接待层安全监听目录。

这里负责输入监听、输出监听、阻断和审计。命中注入、XSS、泄露、异常频控等规则时，可以立即中止 Hermes 对话链路。

禁止事项：

- 不直接生成对用户的回复
- 不接管 Hermes 的对话职责
