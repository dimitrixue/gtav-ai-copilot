# 双人分工与接口契约

## 文件所有权

| 成员 | 主责目录 | 交付内容 |
| --- | --- | --- |
| A：知识库与数据检索工程师 | `data_kb/` | 任务知识库、POI 数据、采集/构建脚本、SQLite 或 LightRAG 适配、`rag_retriever.py` |
| B：客户端与模型工程师 | `copilot_app/`、`gtav-telemetry-mod/` | 遥测 C#、截图、悬浮窗、快捷键、DeepSeek 多模态流式调用 |
| 共同维护 | `docs/`、根目录配置 | 文档、依赖与启动约定；先在 PR 说明中约定负责人 |

默认规则是 A 只改 `data_kb/`，B 只改 `copilot_app/` 和 `gtav-telemetry-mod/`。公共接口通过 PR 讨论后再调整，避免双方同时编辑同一模块。`scripts/` 由提出相应自动化需求的一方维护，跨边界改动先拆成独立 PR。

## 成员 A：知识库与检索

A 负责扩充 `missions_kb.json`，目标范围为 69 个主线任务、58 个支线任务及股票暗杀指南；并可在 `data_kb/` 内实现采集程序、SQLite/LightRAG 索引和离线构建。新增内容应保留来源、版本/平台差异和未核实标记，不把猜测写成确定攻略。

公开接口固定为：

```python
def get_tactical_context(telemetry: dict) -> dict:
    ...
```

入参来自遥测 JSON。返回对象至少包含 `mission_id: str`、`mission: dict`、`nearby_pois: list[dict]`；无匹配资料时返回空对象/列表，不抛出未处理异常。返回 JSON 可序列化，不包含数据库连接、模型对象或 UI 类型。扩展键向后兼容；删除/改名字段须先更新契约并通知 B。

## 成员 B：客户端、遥测与推理

B 负责 `GTAVTelemetryServer.cs` 输出结构、截图/遥测采集、右上角置顶悬浮窗、游戏前台的小键盘 `Num 1` 快捷键和 DeepSeek 流式多模态请求。客户端通过 `get_tactical_context(telemetry)` 取得攻略上下文，不直接依赖 A 的数据库实现。

遥测文件写入 `%TEMP%\gtav_ai_telemetry.json`，UTF-8 JSON，`timestamp` 为 Unix 毫秒。当前字段包括 `protagonist`、`is_mission_active`、`active_mission_script`、`location`、`player_status`、`active_objectives`。字段新增保持兼容；坐标使用 GTA 世界坐标，无法识别时使用显式空值/未知值。

客户端模型配置使用 `DEEPSEEK_API_KEY` 与可选 `DEEPSEEK_MODEL`，默认 `deepseek-flash`。密钥仅放本地 `.env`，不得写入代码、日志、截图或提交。模型建议要区分遥测事实、知识库内容与视觉推断，并明确不确定性。

## 协作与验证

各自从 `main` 拉分支，限定提交在所属目录；跨模块接口变更先开 PR 并给另一成员审阅。合并前至少运行 `python -m compileall data_kb copilot_app scripts`；涉及知识检索时用模拟遥测检查空匹配和命中结果，涉及客户端时另做本地游戏联调。`version_backup/`、游戏安装文件、下载包和 `.env` 永不进入 Git。
