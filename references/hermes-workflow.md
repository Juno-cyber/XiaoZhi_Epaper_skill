# Hermes workflows

仅在 Hermes 定时任务场景读取本文。一般设备操作不依赖 Hermes。
网站调试见 [web-console.md](web-console.md)。

## External data to a custom page

Prefer updating a stable dynamic element ID instead of rebuilding the page:

~~~json
{"tool":"fridge.page.element.control","args":{"action":"update","page":7,"id":"value","text":"new value","refresh":true}}
~~~

Automation should:

- discover and health-check the device at runtime rather than storing an IP;
- use bounded network timeouts;
- validate external data before display;
- send one mutation at a time;
- log success only after checking outer and inner response errors;
- avoid automatic mutation retries after ambiguous timeouts;
- stay quiet when no meaningful data changed, if that matches the job's notification policy.

## Shared cron prompt

Reference [the cron prompt template](../templates/canvas-creativity-cron-prompt.md) from the job instead of embedding a copy. This keeps behavior synchronized with the deployed Skill. Local schedules, delivery preferences, and device selection belong in job configuration rather than in the reusable Skill.

Use the installed template path in the job prompt:

~~~text
严格读取并执行 ~/.hermes/skills/smart-home/xiaozhi-control/templates/canvas-creativity-cron-prompt.md 中「Prompt 正文」的全部指令。
~~~

Create or change schedules only when requested, and report the scheduler's
confirmed result. Scheduler state belongs to Hermes. When using another Agent's
scheduler, adapt its supported tools, template paths and delivery settings.
