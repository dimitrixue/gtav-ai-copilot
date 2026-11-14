# GTA V AI Copilot

双人协作的 GTA V Legacy 遥测攻略助手，包含 SHVDN 遥测脚本、任务知识库检索、桌面悬浮窗与 DeepSeek 多模态流式请求。

知识库来自可追溯的 Wiki 与 GitHub 数据源。重建方式、许可状态、坐标系及目前覆盖差距见 [数据来源说明](docs/DATA_SOURCES.md)；运行 `py scripts\build_full_kb.py` 可更新索引、原生坐标 POI 和任务资料。启动游戏加载遥测脚本后再次运行，可合并引擎 Blip 导出。

## 快速启动

1. 依照 [团队环境 SOP](docs/TEAM_SETUP_GUIDE.md) 部署本机游戏依赖和遥测脚本。
2. 安装 Python 依赖：`py -m pip install -r requirements.txt`。
3. 将 `.env.example` 复制为 `.env`，填入 `DEEPSEEK_API_KEY`。
4. 启动 Story Mode 并验证：`py .\scripts\verify_telemetry.py`。
5. 启动客户端：`py .\copilot_app\overlay_ui.py`。

在游戏里按上排 `2` 或小键盘 `2`，也可以点击悬浮窗里的「问引路人」，即可输入问题。按 `Enter` 发送，按 `Esc` 取消，回复显示在悬浮窗中。小键盘 `Num 1` 用于分析当前游戏画面。

## 双人分工

- **成员 A：知识库与数据检索工程师，只改 `data_kb/`。** 负责 69 个主线、58 个支线任务及股票暗杀攻略的数据扩充，构建 SQLite/LightRAG，并维护 `get_tactical_context(telemetry: dict) -> dict`。
- **成员 B：客户端、遥测与大模型工程师，只改 `copilot_app/` 和 `gtav-telemetry-mod/`。** 负责 C# 遥测、截图、悬浮窗、小键盘 `Num 1` 快捷键及 `deepseek-flash` 多模态流式 API。
- 文档和依赖等公共文件由提出改动的一方维护；跨目录接口变更通过 PR 先确认契约。细节见 [双人协作契约](docs/ARCHITECTURE_COLLAB.md)。

知识库目前包含少量联调样例，覆盖目标需由成员 A 按来源逐步补齐。`.env`、游戏二进制、下载包和 `version_backup/` 不提交。仓库设为 Private 后，可在 **Settings → Collaborators → Add people** 邀请队友。
