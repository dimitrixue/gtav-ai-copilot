# GTA V 遥测与修改器环境复现 SOP

本项目面向 **GTA V Legacy / Steam**。修改器和脚本会改变游戏运行环境；先确认游戏已关闭，并为个人存档留独立备份。不要分发游戏本体、RPF、付费内容或来源不明的存档。

## 先决条件

- Windows、Steam 版 GTA V Legacy，以及可正常启动的 Story Mode。
- Git、Python 3.10+、PowerShell 5.1+；安装 Python 依赖：`py -m pip install -r requirements.txt`。
- 从 ScriptHookV 官方发布页下载 ZIP；从 Rampage 发布页下载明确标注 Legacy 的版本。将两份 ZIP 放入一个本机下载目录。
- 选定合法取得且适用于 Legacy 的 100% 存档文件（通常名为 `SGTA50000`）。存档兼容性取决于版本和个人档案；先备份自己的 Profiles 目录。

## 部署步骤

1. 克隆私人仓库后，在项目根目录运行：

   ```powershell
   .\scripts\setup_teammate.ps1 -DownloadDirectory 'D:\Downloads\GTA-Mods'
   ```

   脚本从 Steam 注册表和 Steam libraryfolders 中检测游戏目录。多档案用户需要再传 `-ProfileId '<Profiles 子目录名>'`。如果所用存档托管在可信 GitHub release，可传 `-LegacySaveUrl '<直链>'`；也可直接把 `SGTA50000` 放在下载目录。脚本从 GitHub `crosire/scripthookvdotnet` 的 `nightly` release 获取 SHVDN。ScriptHookV、Rampage 与存档由用户自行下载并提供。

2. 检查游戏目录中的 `ScriptHookV.dll`、`dinput8.dll`、SHVDN DLL/ASI、`Rampage.asi` 和 `scripts\GTAVTelemetryServer.cs`。首次启动选择 Story Mode，等待 SHVDN 编译脚本。

3. 运行遥测验证：

   ```powershell
   $env:GTAV_GAME_PATH = 'D:\SteamLibrary\steamapps\common\Grand Theft Auto V'
   py .\scripts\verify_telemetry.py
   ```

   验证通过要求依赖文件齐全、SHVDN 日志出现遥测脚本且 `%TEMP%\gtav_ai_telemetry.json` 在 5 秒内更新。若脚本编译失败，查看游戏目录 `ScriptHookVDotNet.log`。

4. 将 `.env.example` 复制为项目根目录 `.env`，填入自己的 `DEEPSEEK_API_KEY`；不要提交 `.env`。启动：

   ```powershell
   py .\copilot_app\overlay_ui.py
   ```

   悬浮窗可置顶。在 GTA 位于前台时按实体小键盘 `1`，分析当前任务、下一步和游戏按键。点击悬浮窗右上角的 × 关闭。接口可用性与模型多模态能力由服务配置决定。

## 备份与恢复

运行 `scripts\backup_and_restore_version.bat` 可备份/恢复批处理所列的 GTA V 版本文件。备份位于项目根 `version_backup/`，约 2.4 GiB，已被 Git 忽略。此备份仅用于本机版本恢复，不要上传仓库或网盘公开分享。

## GitHub 双人协作

仓库使用 Private 可见性。另一名成员在仓库页打开 **Settings → Collaborators**（部分界面显示 **Collaborators and teams**），选择 **Add people**，按 GitHub 用户名/邮箱邀请并等待对方接受。日常按 `docs/ARCHITECTURE_COLLAB.md` 的目录所有权分支开发、PR 合并。
