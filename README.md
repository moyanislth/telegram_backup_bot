# Telegram Resource Backup Bot v3

一个基于 `python-telegram-bot==22.8` 的 Telegram 资源备份机器人。

支持将用户发送的图片、视频、文件、音频、文字等资源自动保存到各自绑定的资源群组，并支持 Telegram Album（相册/多图）和消息链接处理。

---

## 功能简介

- 只有管理员和已授权用户可以使用机器人。
- 管理员可在菜单中管理「用户 → 资源群组」的绑定关系。
- 每个用户的资源自动保存到自己的绑定群组。
- 支持单条消息和 Telegram Album（相册/多图）。
- 支持 `/searchid`：私聊查看自己的 User ID，群内查看群组 Chat ID。
- 机器人被加入群组/频道时自动发送欢迎语（含 Chat ID 与配置指引）。
- 支持发送 Telegram 消息链接（含话题链接），机器人会尝试读取公开/有权限访问的消息。
- 支持 `/cancel` 取消进行中的绑定操作。
- 配置通过 `.env` 环境变量管理。

---

## 目录结构

```text
项目根目录/
├── bot.py                     # 入口文件：初始化日志、数据库，构建 Application 并注册 handlers
├── config.py                  # 配置模块：从 .env 读取 BOT_TOKEN、管理员、默认绑定等
├── database.py                # 数据库模块：SQLite 连接、建表、默认绑定初始化、UTC 时间工具
├── users.py                   # 用户与绑定管理：用户 upsert、绑定查询/设置/删除/列表
├── permissions.py             # 权限模块：管理员判断、用户是否允许使用、拒绝未授权请求
├── resources.py               # 资源去重与记录：生成去重 key、检查存在、保存资源记录、判断资源类型
├── keyboards.py               # 键盘模块：主菜单、绑定管理菜单、取消/确认键盘
├── states.py                  # 状态管理：user_data 状态键定义、设置/清除状态
├── chat_access.py             # 群组访问检查：检查机器人是否有权限访问指定群组
├── helpers.py                 # 辅助函数：安全显示名称、安全编辑回调消息
├── telegram_links.py          # Telegram 消息链接解析（含话题链接）
├── handlers/                  # 所有 Telegram 事件处理器
│   ├── __init__.py            # 空文件，标记为 Python 包
│   ├── commands.py             # /start、/help、/searchid、/cancel 命令处理
│   ├── admin_bindings.py      # 管理员绑定管理：菜单、添加、删除、列表、检查、文本输入流程
│   ├── callbacks.py           # InlineKeyboard 回调统一处理
│   ├── messages.py            # 普通消息入口：权限检查、绑定获取、链接/Album/单条资源分发
│   ├── links.py               # 消息链接处理：复制链接指向的内容到目标群组
│   ├── albums.py              # Album 处理：批量复制相册
│   ├── single_resource.py     # 单条资源处理：复制、保存记录
│   ├── group_events.py        # 群组事件：机器人入群欢迎语
│   └── errors.py              # 全局错误处理：记录未处理异常
├── .env                       # 实际环境变量文件（不要提交到 Git）
├── .env_example               # 环境变量示例文件
└── requirements.txt           # Python 依赖列表
```

---

## 环境要求

- Python 3.9 或更高版本（推荐 Python 3.10+）
- Windows 用户推荐使用 PowerShell 7
- 可访问 Telegram Bot API 的网络环境
- 一个 Telegram Bot Token（从 [@BotFather](https://t.me/BotFather) 获取）
- 你的 Telegram User ID（可通过 [@userinfobot](https://t.me/userinfobot) 获取，或启动机器人后发送 `/searchid`）

---

## 快速开始（PowerShell 7）

### 1. 进入项目目录

```powershell
Set-Location D:\Projects\Py\telegram_backup_bot
```

### 2. 创建虚拟环境

```powershell
py -3.11 -m venv .venv
```

### 3. 启动虚拟环境

```powershell
.\.venv\Scripts\Activate.ps1
```

如果提示“禁止运行脚本”，执行一次以下命令后再激活：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

### 4. 下载依赖

```powershell
pip install -r requirements.txt
```

### 5. 配置环境变量

复制示例文件：

```powershell
Copy-Item .env_example .env
```

至少填写以下内容：

```env
BOT_TOKEN=你的新BotToken
ADMIN_USER_IDS=你的Telegram用户ID
DEFAULT_BINDINGS={"你的用户ID": -100xxxxxxxxxx}
DB_FILE=resource_backup.db
ALBUM_WAIT_SECONDS=3.0
```

各项说明：

- `BOT_TOKEN`：Telegram Bot Token，必填。
- `ADMIN_USER_IDS`：管理员 User ID，多个用英文逗号分隔，例如 `123456789,987654321`。
- `DEFAULT_BINDINGS`：首次启动时自动建立的绑定，JSON 格式，例如 `{"123456789": -1003145884431}`。可为空 `{}`。
- `DB_FILE`：SQLite 数据库文件路径。不设置时默认存放在项目根目录；设置相对路径时相对于启动时的工作目录，建议用绝对路径。
- `ALBUM_WAIT_SECONDS`：Album 等待时间（秒），默认 `3.0`。弱网下相册消息到达间隔可能超过等待窗口，相册会被拆分成多条消息保存。

> ⚠️ 安全提示：`.env` 包含敏感信息，请勿提交到 Git 仓库。建议将 `.env` 加入 `.gitignore`。

### 6. 启动项目

```powershell
python bot.py
```

启动成功后，终端会输出类似日志：

```text
========================================
Telegram Resource Backup Bot v3 启动
管理员: {5822972759}
数据库: D:\Projects\Py\telegram_backup_bot\resource_backup.db
Album 等待: 1.5 秒
========================================
```

### 7. 退出虚拟环境

```powershell
deactivate
```

---

## 一键复制版（PowerShell 7）

```powershell
Set-Location D:\Projects\Py\telegram_backup_bot

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt

Copy-Item .env_example .env
notepad .env

python bot.py
```

---

## 使用说明

### 普通用户

1. 向机器人发送 `/start` 查看自己的 User ID。
2. 将 User ID 发给管理员，由管理员为你绑定资源群组。
3. 绑定成功后，直接发送图片、视频、文件、音频、文字等资源。
4. 机器人会自动保存到你的绑定群组，并回复保存结果。
5. 发送 `/searchid` 可随时查看自己的 Telegram User ID。
6. 也可以发送 Telegram 消息链接（t.me/…），机器人会尝试读取并保存。

### 管理员

1. 邀请机器人到目标群组/频道，并**将机器人设为管理员**（必需）。
2. 机器人入群后会自动发送欢迎语，包含该群组的 Chat ID；也可在群内发送 `/searchid` 随时查看。
3. 私聊机器人发送 `/start`，点击「⚙️ 绑定管理」。
4. 可添加/修改绑定、删除绑定、查看全部绑定、检查群组。
5. 添加绑定时，先输入用户 User ID，再输入资源群组 Chat ID。
6. 机器人会检查群组访问权限（要求机器人为管理员），确认无误后点击「✅ 确认绑定」。
7. 若该用户已有绑定，确认文案会显示覆盖警告。
8. 任意输入流程中可发送 `/cancel` 取消当前操作。

> 机器人必须在目标资源群组中是管理员，否则绑定校验不通过。

---

## 注意事项

- Bot API 无法绕过 Telegram 的受保护内容、禁止保存/转发限制，也无法访问机器人没有权限读取的消息。
- 机器人只处理私聊消息，群组内消息不会被当作资源保存。
- 数据库文件保存了用户和绑定关系，请定期备份。
- 如果更换 Bot Token，请及时更新 `.env` 并重启机器人。
- 如果机器人无法保存资源，请检查：
  - 机器人是否在目标群组中，且被设为管理员；
  - 目标群组 Chat ID 是否正确；
  - 源消息是否允许复制/转发。

---

## 常见问题

### `python` 命令无输出或报错

Windows 上可能存在 Microsoft Store 的 `python.exe` 占位符。可执行：

```powershell
where.exe python
```

如果第一行是 `WindowsApps\python.exe`，说明命中了占位符。可以：

- 使用 `py` 命令代替，例如 `py -3.11 -m venv .venv`；
- 或者打开「设置 → 应用 → 高级应用设置 → 应用执行别名」，关闭 `python.exe` 和 `python3.exe`。

### 激活虚拟环境报“禁止运行脚本”

执行一次：

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

然后重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

### 不同终端的激活命令

| 终端         | 激活命令                        |
| ------------ | ------------------------------- |
| PowerShell 7 | `.\.venv\Scripts\Activate.ps1`  |
| CMD          | `.venv\Scripts\activate.bat`    |
| Git Bash     | `source .venv/Scripts/activate` |
| Linux/macOS  | `source .venv/bin/activate`     |

---

## 依赖版本

```text
python-telegram-bot==22.8
python-dotenv==1.0.1
```

---

## 许可证

本项目仅供个人学习与使用，请遵守 Telegram 服务条款及相关法律法规。
