# dispatch/workflow_runtime

workflow 运行内核目录。

这里保留真正需要执行的底座能力：dispatcher、poller、worker、scheduler、recovery、realtime、snapshot。

说明：

- 这是执行内核，必须保留
- 旧的工作流产品壳和可视化模块不属于当前保留范围
- `internal_event_delivery_poller_service.py` 也归属于这个运行内核
