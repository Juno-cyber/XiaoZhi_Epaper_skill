# Hermes workflows

## Local web-console testing

Use the repository copy of Litsea_Top when it is available:

~~~bash
cd ~/Gitproject/Litsea_Top
XIAOZHI_TARGET=http://<device-host>:8080/ python3 deploy/proxy_server.py 9876
~~~

Open http://127.0.0.1:9876/xiaozhi.html. The development proxy is intentionally loopback-only by default. Set LITSEA_PROXY_BIND only when another trusted LAN host must access it; never expose it publicly.

Without a real device, run the proxy integration tests against their mock HTTP device:

~~~bash
python3 -m unittest discover -s ~/Gitproject/Litsea_Top/tests -v
~~~

For a real-device smoke test:

1. Verify GET / identity and firmware version.
2. Load the console and connect through /xiaozhi-api/.
3. Exercise one read-only call.
4. Test page 6 and a disposable custom page with a small batched layout.
5. List elements after each mutation and verify the browser reports inner MCP errors.
6. Upload a small 1-bpp image and verify list/download/render.
7. Power-cycle only when persistence testing is explicitly intended.

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

Reference templates/canvas-creativity-cron-prompt.md from the job instead of embedding a copy. This keeps behavior synchronized with the deployed Skill. Local schedules, delivery preferences, and device selection belong in job configuration rather than in the reusable Skill.

Put the visualization marker before the reference line:

~~~text
[XIAOZHI_CRON_META v1 page=6 mode=canvas-refresh]
严格读取并执行 ~/.hermes/skills/smart-home/xiaozhi-control/templates/canvas-creativity-cron-prompt.md 中「Prompt 正文」的全部指令。
~~~

After the scheduler confirms a create or update, run
`python3 scripts/workflow_map.py --discover` and return the generated SVG in
the same conversation when the channel supports images or file attachments.
