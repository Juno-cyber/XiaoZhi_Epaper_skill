# XiaoZhi E-Paper Skill

让 Agent 通过局域网操控小智墨水屏。支持画布、自定义页面、时钟、图片、冰箱数据、设备名称与常驻页设置。

**Agent 从 [SKILL.md](SKILL.md) 开始，不需要通读仓库。** 当前契约对齐固件 2.5.2.1 与 Litsea_Top 2026-10-18 版本；旧版 2.0.7/2.0.8 的聚合工具继续适用，新增 HTTP 功能以实际固件为准。

## 快速使用

核心只需要 Python 3.10+，无需安装 Python 依赖。以下命令从仓库根目录执行；Windows 使用 `py -3 -X utf8` 替代 `python3`，布局和参数保存成 UTF-8 文件，避免不同 Shell 的引号差异。

```bash
python3 scripts/xiaozhi_discovery.py --json --save
python3 scripts/xiaozhi.py DEVICE_IP health
python3 scripts/xiaozhi.py DEVICE_IP pages
python3 scripts/xiaozhi.py DEVICE_IP elements 6
```

将 `DEVICE_IP` 替换为发现结果中选定的地址。整页显示：

```bash
python3 scripts/quick_page_builder.py DEVICE_IP 6 templates/hello.layout --check
python3 scripts/quick_page_builder.py DEVICE_IP 6 templates/hello.layout --backup before.json
```

第一条仅离线校验；第二条会替换画布页内容、校验回读结果，再请求一次显示。`before.json` 保存修改前的元素，可用于恢复。原有自定义页面不受这个示例影响。

其他常用操作：

```bash
python3 scripts/xiaozhi.py DEVICE_IP show 5
python3 scripts/xiaozhi.py DEVICE_IP home
python3 scripts/xiaozhi.py DEVICE_IP home --page 5 --timeout-min 2
python3 scripts/xiaozhi.py DEVICE_IP name --set "书桌小智"
```

`timeout-min 0` 关闭自动返回；设置常驻页本身不会切页。完整参数见 [API](references/api-reference.md)。

## 安装到 Agent

仓库是维护来源，安装副本由脚本同步；不自动提交、推送或创建定时任务。

```bash
python3 scripts/install_skill.py --agent hermes --dry-run
python3 scripts/install_skill.py --agent hermes
python3 scripts/install_skill.py --agent codex
python3 scripts/install_skill.py --target /path/to/your-agent/skills/xiaozhi-control
```

默认分别安装到 `~/.hermes/skills/smart-home/xiaozhi-control` 和 `$CODEX_HOME/skills/xiaozhi-control`（未设置时为 `~/.codex/skills/xiaozhi-control`）。`--target` 或 `XIAOZHI_SKILL_DIR` 可指定其他运行环境。旧命令 `bash deploy.sh` 继续调用同一个安装器。安装会清理受管理目录里的过期同类文件，拒绝符号链接与危险路径。

## 发现与刷新

- 发现顺序：已验证缓存 → mDNS → UDP → 本机网段。已知地址读探测最多重试一次；扫描默认 16 并发、每地址 2 秒，控制请求仍串行。
- 找不到时：`--host IP` 直接探测，或 `--subnet 192.168.1.0/24 --scan-timeout 4`。网络范围需来自本机/用户，不盲扫常见网段；显式网段也约束缓存和 mDNS 候选，跳过 Linux 已断开的接口。
- 缓存：Linux/macOS 为 `$XDG_CACHE_HOME/xiaozhi/devices.txt`（默认 `~/.cache`）；Windows 为 `%LOCALAPPDATA%/xiaozhi/devices.txt`。可设 `XIAOZHI_CACHE_FILE`，兼容读取旧 Hermes 缓存。缓存只提供候选地址，每次重新验证。
- Linux 使用接口信息，macOS 使用 `ifconfig`/可选 `dns-sd`，Windows 使用 PowerShell 网络 JSON；均可用 `--host`/`--subnet` 兜底。
- 布局始终先写后显示。`switch + refresh` 被合并为最后一次显示请求。HTTP 返回与回读确认的是设备状态，屏幕实际完成仍需观察或串口日志；全刷波形的多阶段闪烁并不等于提交了两次。

控制服务无认证，只用于可信局域网；不要把 8080 或本地代理暴露到公网。故障排查见 [pitfalls.md](references/pitfalls.md)。

## 可选功能与验证

- `pixel_art_generator.py`：25 个内置 24×24 图标。
- `zentangle_generator.py`：程序化线稿；依赖 NumPy，PNG 预览另需 Pillow。
- `quote_fetcher.py`：文案与去重。`crash_log.py`：串口日志，需要 pyserial。
- 定时刷新仅在用户需要时配置；使用 Hermes 时按需读取 [定时任务说明](references/hermes-workflow.md) 和共享模板。
- 深入开发分别查看固件和网站自己的文档；本仓库仅保留 [固件索引](references/firmware-development.md) 与 [网站索引](references/web-console.md)，减少过时实现副本。

```bash
python3 -m unittest discover -s tests -v
python3 scripts/quick_page_builder.py 127.0.0.1 6 templates/hello.layout --check
```

可选依赖：`python3 -m pip install -r requirements-optional.txt`。Linux 可直接运行全套测试；跨系统核心测试见 `tests/test_control.py`，Windows/macOS 专用分支用模拟输入覆盖，实际环境仍需验证。

2026-10-18 真机验证（固件 2.5.2.1）：发现设备成功；画布 6 个元素回读一致；包含旧式 `switch + refresh` 的布局只发送一次最终显示请求，用户现场确认第二轮测试只刷新一次、显示正常。串口因系统权限不可读取，未取得驱动刷新日志；本次未测试重启持久化，也未修改或烧录固件。

License: MIT
