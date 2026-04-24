# platform/security

平台安全目录。

这里统一承载平台级加密、脱敏、安全策略执行等安全基础能力。

- `encryption_service.py`：平台统一加解密能力。
- `content_policy.py`：通用敏感内容识别与脱敏规则引擎，供接待安全监听、组织记忆治理等多个模块复用，原先位于 `app/core/content_policy.py`。
