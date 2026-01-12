# TuneBot

Telegram 音乐搜索与归档机器人，支持多平台音源聚合搜索、下载，并自动归档到私人频道。

## 功能特性

- 🔍 **聚合搜索** - 支持网易云、酷我、QQ音乐等多平台搜索
- 📥 **多音质下载** - 支持 128k、320k、FLAC、FLAC 24bit
- 📁 **自动归档** - 下载的音乐自动转发到私人频道
- ❤️ **收藏夹** - 收藏喜欢的歌曲，方便再次下载
- 📜 **历史记录** - 查看下载历史，支持快速重发
- 📊 **排行榜** - 浏览各平台热门排行榜
- 🔄 **智能降级** - 高音质不可用时自动降级
- 🏷️ **标签搜索** - 归档消息自动添加多个标签便于搜索

## 快速开始

### 使用 Docker Compose（推荐）

1. 创建配置文件：

```bash
mkdir tunebot && cd tunebot

# 创建 .env 文件
cat > .env << 'EOF'
BOT_TOKEN=your_bot_token_here
ARCHIVE_CHANNEL_ID=-100xxxxxxxxxx
ALLOWED_USER_IDS=your_user_id
DEFAULT_QUALITY=320k
LOG_LEVEL=INFO
EOF

# 下载 docker-compose 文件
curl -O https://raw.githubusercontent.com/GLH08/TuneBot/main/docker-compose.remote.yml
```

2. 启动服务：

```bash
docker compose -f docker-compose.remote.yml up -d
```

### 从源码构建

```bash
git clone https://github.com/GLH08/TuneBot.git
cd TuneBot
cp .env.example .env
# 编辑 .env 填入你的配置
docker compose up -d --build
```

## 配置说明

| 变量 | 说明 | 必填 |
|------|------|------|
| `BOT_TOKEN` | Telegram Bot Token（从 @BotFather 获取） | ✅ |
| `TELEGRAM_API_ID` | Telegram API ID（从 https://my.telegram.org 获取，用于解除 50MB 限制） | ❌ |
| `TELEGRAM_API_HASH` | Telegram API Hash（从 https://my.telegram.org 获取） | ❌ |
| `ARCHIVE_CHANNEL_ID` | 归档频道 ID（以 -100 开头） | ❌ |
| `ALLOWED_USER_IDS` | 允许使用的用户 ID，多个用逗号分隔 | ❌ |
| `DEFAULT_QUALITY` | 默认音质：128k, 320k, flac, flac24bit | ❌ |
| `API_BASE_URL` | TuneHub API 地址 | ❌ |
| `LOG_LEVEL` | 日志级别：DEBUG, INFO, WARNING, ERROR | ❌ |

### 大文件上传（解除 50MB 限制）

默认情况下，Telegram Bot API 限制文件大小为 50MB。如需上传更大的文件（如 FLAC 24bit），请配置：

1. 访问 https://my.telegram.org 登录
2. 进入 "API development tools"
3. 创建应用获取 `API_ID` 和 `API_HASH`
4. 在 `.env` 中配置这两个变量

配置后可上传最大 2GB 的文件。

## 使用方法

### 基础命令

| 命令 | 说明 |
|------|------|
| `/start` | 开始使用 |
| `/search <歌名>` | 搜索歌曲 |
| `/quality` | 切换下载音质 |
| `/fav` | 查看收藏夹 |
| `/history` | 查看下载历史 |
| `/top` | 浏览排行榜 |
| `/help` | 获取帮助 |

### 使用流程

1. 发送 `/search 歌名` 搜索歌曲
2. 点击搜索结果中的歌曲下载
3. 下载完成后可选择收藏
4. 音乐自动归档到设置的频道

### Inline 模式

在任意聊天中输入 `@你的机器人用户名 歌名` 即可快速搜索。

## 开发

### 项目结构

```
TuneBot/
├── bot.py              # 主程序入口
├── config.py           # 配置模块
├── utils/
│   ├── __init__.py
│   ├── api_client.py   # TuneHub API 客户端
│   ├── db.py           # SQLite 数据库操作
│   └── formatters.py   # 消息格式化
├── Dockerfile
├── docker-compose.yml
├── docker-compose.remote.yml
├── requirements.txt
└── .env.example
```

### 本地开发

```bash
# 安装依赖
pip install -r requirements.txt

# 设置环境变量
export BOT_TOKEN=your_token
export LOG_LEVEL=DEBUG

# 运行
python bot.py
```

## 技术栈

- Python 3.10+
- python-telegram-bot 20+
- Pyrogram (用于大文件上传)
- aiohttp
- aiosqlite
- TuneHub API

## 许可证

MIT License
