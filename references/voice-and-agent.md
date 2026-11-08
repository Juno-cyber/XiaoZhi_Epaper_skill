# Voice modes and local Agent API

Read this reference only for voice-mode configuration, Qwen realtime access,
scheduled tasks, memory, or session management. Firmware baseline: 2.5.2.9.

## Standard and Qwen realtime voice

`GET /api/voice_config` returns the saved mode and the currently running mode.
The response includes `revision`, `mode`, `active_mode`, `realtime_url`,
`realtime_model`, `realtime_voice`, `system_prompt`, `silence_ms`, `barge_in`,
`tools_enabled`, `api_key_set`, `restart_required`, and `storage_error`. It never
returns the API key.

Read with:

```bash
python3 scripts/xiaozhi.py DEVICE_IP voice-config
```

Writes are revisioned. Read first, put the latest integer `revision` and only the
fields being changed in a UTF-8 JSON file, then submit it:

```json
{"revision":12,"mode":"qwen","realtime_api_key":"USER_SECRET"}
```

```bash
python3 scripts/xiaozhi.py DEVICE_IP voice-config --config-file voice-patch.json
```

Do not place API keys in chat, command-line arguments, logs, templates, or the
repository. An empty `realtime_api_key` preserves the saved key; `null` clears
it. A stale revision is rejected. Save success means the next connection can use
the configuration; mode changes require a restart and the CLI never restarts the
device automatically.

Supported API mode values are `xiaozhi` (standard voice) and `qwen` (Qwen realtime).
The Qwen URL must be WSS,
at most 512 bytes, and must not contain a query string. New devices expose this
template until a real workspace is configured:

```text
wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/realtime
```

Do not attempt to connect to the literal template. Selecting Qwen with a missing
URL or key is allowed for configuration but produces a device prompt instead of
a connection. Model and voice IDs must match the account's permissions; changing
only a URL does not adapt another vendor's event or audio protocol.

The `voice` command controls the standard voice WebSocket URL through
`/api/websocket_url`. Both voice modes still perform OTA checks while
preserving their saved voice configuration and ignoring OTA activation/voice
overrides. Voice mode never changes the OTA address, Wi-Fi, screen layouts, or
AEC settings.

## Local Agent management

`POST /api/agent` is a management API. A request without `--request-file` sends
`{"op":"get"}` and is read-only:

```bash
python3 scripts/xiaozhi.py DEVICE_IP agent
```

For an explicitly requested mutation, place the exact request in a JSON file:

```bash
python3 scripts/xiaozhi.py DEVICE_IP agent --request-file agent-request.json
```

Supported operations include `config`, `tasks`, `memory`, `session_clear`, and
`dream`. Read current state and revision before configuration writes. Do not
automatically retry an ambiguous task creation: list tasks first because the
request may already have succeeded. Task IDs must come from a fresh list.

Tasks require Qwen or Agent mode after restart. Firmware 2.5.2.9 supports at most
eight tasks and requires a `task_type`:

- `reminder`: speak the supplied reminder, without tools.
- `search`: one bounded web search; `result_limit` is 1–3.
- `control`: one `volume` or `page` action with the exact saved value.

The management API cannot grant arbitrary shell, HTTP, drawing, or remote-code
execution. Voice-driven canvas creation and element editing remain disabled;
use the manual page APIs in this skill. Memory changes and session clearing need
the user's specific request and should be read back after mutation.

`GET /api/agent/session_log?mode=pipeline|realtime` exports NDJSON and may contain
conversation history. Treat it as sensitive user data and do not collect or
transmit it unless the user requests that export.
