# Hermes Environment Workflows

> Hermes 运行环境特有的工作流（Web 控制台设计/测试、外部数据推送）。通用 API 与工具用法见 SKILL.md 主文件。

---

## Web Design & Testing Workflow

When optimizing or testing the web console UI, use this workflow. The user has Claude Code configured locally with Playwright MCP and chrome-devtools MCP (`.mcp.json` in `<web-project-dir>/`), and wants web design work delegated to Claude Code going forward.

### 1. Design Optimization (Claude Code Print Mode)

Use Claude Code in print mode (`-p`) to optimize HTML/JS/CSS files. This is the preferred approach when the user has Claude Code configured with project MCP servers (`.mcp.json`).

```bash
claude -p "Optimize xiaozhi.html and js/xiaozhi.js for better visual design.
Keep existing functionality, only improve design.
Use CSS variables from css/style.css." \
  --allowedTools "Read,Edit,Write,Bash" \
  --max-turns 20 \
  --output-format json
```

Key points:
- Set `workdir` to the web project directory (e.g. `<web-project-dir>`)
- Use `--allowedTools` to restrict to Read/Edit/Write/Bash (no MCP needed for pure file editing)
- `--output-format json` gives cost/turns tracking
- Print mode skips all interactive dialogs — no tmux needed
- **Pitfall**: long `claude -p` invocations with large prompt strings hit the consent timeout. Write prompt to a file first and pipe it, or use `delegate_task` for complex multi-step tasks.

### 2. Functional Testing (Hermes Browser Tools or delegate_task)

For testing the web console against the live ESP32 device, use Hermes's native browser tools (`browser_navigate`, `browser_click`, `browser_console`, `browser_snapshot`) rather than trying to run Claude Code with Playwright MCP. Hermes browser tools are simpler and don't require MCP configuration.

Alternatively, `delegate_task` with `toolsets: ["browser", "terminal", "file"]` runs browser testing in the background.

**Pitfall — long claude -p commands get blocked by timeout**: When invoking `claude -p "very long prompt..."` with a long prompt string, the command is likely to hit the consent-timeout because it looks unfamiliar. **Workaround**: write the prompt to a temp file (`/tmp/claude_prompt.txt`) and use `cat /tmp/claude_prompt.txt | claude -p` piped input, or better yet use `delegate_task` to run the testing in the background — delegate_task is not subject to the same foreground timeout restrictions.

Test sequence:
1. Start HTTP proxy (see pitfall #15 below about HTTPS)
2. `browser_navigate` to the page
3. `browser_click` connect button, verify status via `browser_console` expression
4. Test each tab (page switch / fridge / canvas) by clicking and checking console/DOM
5. Use `browser_console` with `expression` param to run inline JS fetch calls to verify API path
6. When a click doesn't produce visible DOM changes, use `browser_console` with `expression` to inspect element innerHTML — the accessibility tree snapshot may not show rendered content (e.g. food cards, stat cards) even when they're correctly rendered in the DOM
7. For canvas freehand drawing / image insertion features, test the full bitmap pipeline: draw on canvas → `getImageData` → `pixelsTo1bpp` → `POST /api/canvas_image?name=test` → `fridge.canvas.control` action=`add_image` → verify device returns `{"status":"success"}` and image appears in `GET /api/canvas_image` list

### 3. CLAUDE.md for Context

Create a `CLAUDE.md` in the web project root so Claude Code knows the project structure, API endpoints, and tool names. This saves correction cycles — Claude Code reads it automatically.

### 4. Delegation for Long-Running Web Tasks

When Claude Code print mode (`claude -p`) gets blocked by consent timeouts (common with long prompts), use `delegate_task` instead. A delegated subagent with `toolsets: ["browser", "terminal", "file"]` can:
- Navigate to the web page using Hermes browser tools
- Edit files using file tools
- Run shell commands using terminal tools
- It runs in the background and results re-enter the conversation automatically

This is especially useful for complex multi-step web design + testing tasks that would otherwise exceed foreground tool-call limits.


---

## External Data → E-Paper via Cron (Gold Price Pattern)

A reusable pattern for pushing external API data to the e-paper display using
a shell script + `no_agent=true` cron job:

1. **Shell script** (`scripts/gold_price_update.sh`):
   - Fetch data from free API (no key needed)
   - Parse JSON with python3 one-liner
   - Push to device via `curl -X POST /api/call`
   - Echo result string (delivered to user by cron)

2. **Cron job** (`no_agent=true`, `script=gold_price_update.sh`):
   - `schedule: "every 1h"` or `"0 * * * *"`
   - `deliver: "origin"` (or `"local"` for silent)
   - Script runs without LLM — pure bash + curl + python3

3. **Gold price API**: `https://api.gold-api.com/price/XAU/CNY`
   - Returns `{"price": 27748.35, "currency":"CNY", ...}` (CNY per troy oz)
   - Convert to per-gram: `price / 31.1035` (1 troy oz = 31.1035g)
   - Free, no API key, no rate limit issues at 1req/hour

4. **Layout**: Gold price zone on right side of split-screen page:
   - `gold_title` text "黄金¥/g" at (192, 2) font=12
   - `gold_price` text "¥892.6/g" at (192, 24) font=12, dynamic
   - `gold_time` text "08:39更新" at (192, 42) font=10(→12), dynamic
