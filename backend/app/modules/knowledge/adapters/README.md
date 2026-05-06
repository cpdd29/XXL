# knowledge/adapters

知识源适配器层。

首版只服务 `Obsidian` 本地文件系统知识源，后续如果扩展到其他知识源，也统一落在这里。

首版建议适配器：

- `obsidian_fs_adapter.py`

职责：

- 读取注册过的 vault 路径
- 遍历 Markdown 文件
- 返回平台可消费的原始文件结构

当前已落地：

- `obsidian_fs_adapter.py`
  - 校验 vault 本地目录
  - 扫描 `.md` / `.markdown`
  - 跳过 `.obsidian` 等隐藏目录
  - 返回原始 Markdown、相对路径、校验和、更新时间等信息

本层不做：

- 文档切片
- 检索打分
- 接待链注入
