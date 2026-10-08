## Description
Real-browser automation (JS/SPA pages, screenshots, downloads) and OS accessibility (read/act on web pages and native desktop apps) via the fastbrowser CLI, driven with run_shell.

## Parameters
None — this is a document skill; read it, then run the commands below with run_shell.

Discover the CLI commands and the full underlying tool list (100+) via run_shell:
- `python3 -m fastbrowser --help` — all CLI commands
- `python3 -m fastbrowser <command> --help` — options for one command
- `python3 -m fastbrowser tools --mode names` — all tool names
- `python3 -m fastbrowser tools --mode compact` — name + short description + param names
- `python3 -m fastbrowser tools --mode help --name <tool>` — one tool's full schema

## Example

Run every command below with the `run_shell` tool, e.g.
`run_shell("python3 -m fastbrowser fetch https://example.com", timeout=120)`.
Give it a generous `timeout` — the browser cold start can take a few seconds.

### Render a JS page to text (one-shot)
```bash
python3 -m fastbrowser fetch "https://example.com" --max-chars 4000
```

### Multi-step in one shot
`--steps` is a JSON array of `{"tool": <name>, "args": {...}}`:
```bash
python3 -m fastbrowser run --url "https://example.com/login" --steps '[
  {"tool":"type","args":{"selector":"#user","text":"admin"}},
  {"tool":"click","args":{"selector":"button[type=submit]"}},
  {"tool":"extract_text","args":{"max_chars":2000}}
]'
```

### Interactive session (auto daemon; state persists across calls)
```bash
python3 -m fastbrowser open "https://example.com"
python3 -m fastbrowser call get_page_title
python3 -m fastbrowser call extract_text --args '{"max_chars":1000}'
python3 -m fastbrowser daemon stop
```

### Screenshots, downloads, JS
```bash
python3 -m fastbrowser screenshot /tmp/page.png
python3 -m fastbrowser download "https://host/img.jpg" /tmp/img.jpg --referer "https://host/page"
python3 -m fastbrowser call execute_js --args '{"script":"document.title"}'
python3 -m fastbrowser call execute_js --args '{"function":"async () => { return 42; }"}'
```

### Discover and call any tool (100+)
```bash
python3 -m fastbrowser tools --mode compact
python3 -m fastbrowser tools --mode help --name navigate
python3 -m fastbrowser call <tool> --args '<json>'
```

### Accessibility (web + native desktop)
```bash
python3 -m fastbrowser ax list
python3 -m fastbrowser ax snapshot
python3 -m fastbrowser ax snapshot --target "desktop:1234"
python3 -m fastbrowser ax act --action click --ref "web:1:ax:42"
python3 -m fastbrowser ax act --action type --ref "desktop:1234:0.1" --text "hello"
python3 -m fastbrowser ax act --action press_key --key "Tab"
```
`ax list` shows surfaces (`web:<tab>`, `desktop:<pid>`); `ax snapshot` returns a UiNode tree plus a readable `text` field. Web refs look like `web:<tab>:ax:<id>`; native desktop refs like `desktop:<pid>:<path>`. Desktop accessibility needs no Chromium, but on macOS requires the "Accessibility" permission.

## Prerequisites
Check the package is installed in the interpreter fastclaw uses; install if missing:
```bash
python3 -c "import fastbrowser; print(fastbrowser.__version__)" || python3 -m pip install fastbrowser
```
Chromium/Chrome is auto-discovered (or set `CHROME_PATH`, or attach an existing browser with `--cdp-url`).

## Notes
- Output is JSON on stdout — parse it directly.
- Give `run_shell` a generous `timeout` (browser cold start takes a few seconds): `run_shell("python3 -m fastbrowser open ...", timeout=120)`.
- If a result has `blocked: true` (WAF/anti-bot) or empty content, try the site's mobile/API endpoint or `fetch`/`curl`.
- Run `daemon stop` when finished; the daemon also exits after being idle.
