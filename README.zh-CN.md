# Sun-Panel Skill + MCP

[English](README.md)

通过 AI、命令行或本地 stdio MCP 管理 Sun-Panel 导航入口。Skill 和 MCP 共用同一个客户端，不需要更换现有面板。

## 支持范围

- 查询版本、列出分组、查询单个分组和入口。
- 预览、新增和修改入口，包括标题、链接、内网链接、图标、描述和归属分组。
- MCP 默认提供 6 个只读/预览工具；启用写入后提供 8 个工具。
- 修改操作要求稳定版 Sun-Panel 1.8.1+，避免旧版部分字段更新破坏原图标的问题。

封装不提供删除入口、列出全部入口、创建分组、排序、布局、壁纸或 Docker 控制。它维护的是导航链接，不会安装链接背后的应用。

## 安装和配置

需要 Python 3.11+。CLI 无额外依赖，MCP 需要 `python -m pip install -r requirements.txt`。

把仓库中的 `sun-panel/` 文件夹复制到技能目录，例如 `~/.codex/skills/sun-panel/`；配置了 `CODEX_HOME` 时使用对应的 `skills` 目录。按客户端要求重新加载技能。也可以直接运行 CLI，或按 `mcp.example.json` 接入支持 stdio 的 MCP 客户端。

连接参数通过运行进程的环境变量提供：

| 变量 | 说明 |
|---|---|
| `SUN_PANEL_BASE_URL` | 自己的面板地址或完整 `/openapi/v1` 地址 |
| `SUN_PANEL_TOKEN` | Sun-Panel OpenAPI 令牌 |
| `SUN_PANEL_ALLOW_HTTP` | 只有明确使用 HTTP 时才设为 `1` |

PowerShell 可临时输入令牌，不把它写入命令历史：

```powershell
$env:SUN_PANEL_BASE_URL = 'https://panel.example.com/openapi/v1'
$panelSecure = Read-Host 'Sun-Panel OpenAPI Token' -AsSecureString
$env:SUN_PANEL_TOKEN = [System.Net.NetworkCredential]::new('', $panelSecure).Password
python sun-panel/scripts/sun_panel.py version
python sun-panel/scripts/sun_panel.py groups
# 用完后清除：
Remove-Item Env:SUN_PANEL_TOKEN
```

所有示例地址均为占位符，仓库不包含可直接连接的个人面板配置或令牌。客户端默认直连，不读取系统代理；不会关闭 HTTPS 证书验证。收到 Lucky 等 HTML 认证页时需要配置适合机器访问的 API 认证方式，不应直接判定令牌失效。

## 使用方式

新入口必须设置稳定、唯一的 `onlyName`，显示标题不等于标识。现有入口没有标识时，公开接口不能按标题查找，也不能列出全部入口。

先修改 `examples/entry.json` 中的地址和分组 ID，再预览：

```text
python sun-panel/scripts/sun_panel.py create --file examples/entry.json
python sun-panel/scripts/sun_panel.py create --file examples/entry.json --yes
python sun-panel/scripts/sun_panel.py update --file examples/changes.json
python sun-panel/scripts/sun_panel.py update --file examples/changes.json --yes
```

不加 `--yes` 时只读预览。修改只发送明确指定的字段，其他字段由面板保留。空字符串表示主动清空可选文本。

MCP 配置示例中要替换 Python 和脚本的绝对路径，并通过客户端的机密配置或启动进程环境传入令牌。已打开的客户端通常不会继承后来设置的变量。默认只有只读和预览工具；脚本参数加 `--allow-write` 后才会出现创建/修改工具。具体修改仍需要符合用户当前请求。

## 图标验证与重试

实测某些 1.8.1 实例查询入口时返回空 `iconUrl`，但页面已正常显示图标。这时结果会标记 `needs_visual_check`，列出未验证的图标字段。请检查页面上的实际图片加载，不要把空读回值当成失败后反复写入。

`executed=true` 表示 API 接受了修改，`verified=true` 表示请求字段已由 API 读回确认。CLI 返回码 `3` 表示已接受写入但仍需检查；返回码 `1` 表示请求或校验错误。网络中断后先查看目标状态，不自动重试写入。

仓库测试全部使用本机模拟服务器，不访问真实 NAS。开发时另行在 1.8.1 上验证过创建入口、修改图标和图片实际加载。项目与 Sun-Panel 官方没有隶属关系。

完整工具列表、运行方式和测试命令见 [英文说明](README.md)，接口摘要见 [api.md](sun-panel/references/api.md)。
