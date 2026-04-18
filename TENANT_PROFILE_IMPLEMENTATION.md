# 租户人员画像改造成果说明

## 当前状态

- [x] 已完成的任务：后端 `profiles` 接口按租户隔离返回画像数据
- [x] 已完成的任务：前端“用户管理”语义重构为“人员画像”
- [x] 已完成的任务：列表页支持租户筛选、搜索、空状态与当前租户导出
- [x] 已完成的任务：详情页重构为画像详情，只保留标签/备注/语言偏好编辑
- [x] 已完成的任务：控制台账号与业务画像职责拆分
- [x] 已完成的任务：补充 tenant profile backfill / rollback 脚本与测试

## 业务定义

- 租户：购买系统的公司，也是画像隔离的一级边界。
- 人员画像：租户下真实使用机器人产生的业务人物，不参与后台登录。
- 后台账号：控制台登录账号，只用于平台管理员、租户管理员等控制面操作者。

## 数据关系

- `tenant -> user_profiles -> platform_accounts`
- `users` 只承担控制台登录账号职责。
- `user_profiles` 只承担业务人物画像职责。
- `conversation_messages.user_id == profile.id` 作为消息与画像的主关联。
- `tasks.user_key == profile.id` 作为任务与画像的主关联。
- 审计事件通过 `user/details/metadata` 中的画像标识、租户标识、平台账号做候选聚合。

## 唯一键与隔离规则

- 同名人员跨租户不合并。
- 同一 `platform + account_id` 跨租户不合并。
- 同租户内优先按 `platform + account_id` 归并画像。
- 无明确租户来源时，回落到默认租户并在迁移报告里保留分配来源。
- 平台管理员可跨租户查看；租户管理员、运营、查看者默认只看自身租户。

## 已落地实现

- 前端导航文案已调整为“人员画像”。
- `/users` 页面已改为“租户下人员画像列表”。
- `/users/[userId]` 页面已改为“画像详情”。
- 前端已切换到真实接口：`/api/profiles`、`/api/profiles/tenants`。
- 画像详情只允许维护 `tags / notes / preferred_language`。
- 导出仅针对当前选中的具体租户，不对“全部租户”开放直接导出。

## 数据迁移脚本

- 规划 / 预演：
  - `python3 backend/scripts/backfill_tenant_profiles.py plan --database-url <DB_URL>`
- 执行 backfill：
  - `python3 backend/scripts/backfill_tenant_profiles.py apply --database-url <DB_URL>`
- 指定映射覆盖：
  - `python3 backend/scripts/backfill_tenant_profiles.py apply --database-url <DB_URL> --override-file <path/to/tenant_overrides.json>`
- 按快照回滚：
  - `python3 backend/scripts/backfill_tenant_profiles.py rollback --database-url <DB_URL> --snapshot-path <snapshot.json>`

### override-file 结构

```json
{
  "profiles": {
    "profile-1": {
      "tenant_id": "tenant-alpha",
      "tenant_name": "Alpha Corp",
      "tenant_status": "active"
    }
  },
  "platform_accounts": {
    "telegram:alice": {
      "tenant_id": "tenant-alpha",
      "tenant_name": "Alpha Corp",
      "tenant_status": "active"
    }
  },
  "channels": {
    "telegram": {
      "tenant_id": "tenant-global",
      "tenant_name": "Global Service",
      "tenant_status": "active"
    }
  }
}
```

## 开发日志

- [完成] 后端画像接口收口：新增 `profiles` schema、service、route，并补齐租户过滤、详情校验、导出与 activity 聚合。
- [完成] 消息接入链路补租户：消息画像自动落库时同步 `tenant_id / tenant_name / tenant_status / last_active_at`。
- [完成] 前端页面语义重构：列表页与详情页从“账号管理”切换为“租户下人员画像管理”。
- [完成] 数据迁移能力补齐：新增 `backend/scripts/backfill_tenant_profiles.py` 与配套测试，支持计划、执行、快照和回滚。
