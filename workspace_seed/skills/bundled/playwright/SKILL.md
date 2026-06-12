## Description
Browser automation using Playwright. Navigate pages, extract content, take screenshots, fill forms, and more.

## Parameters
- url: Target URL (required)
- func: Function name for multi-function skills: "run", "browser_automation", "scrape_dynamic_page", "take_screenshot", "test_element_exists"
- action: "navigate" (default) | "screenshot"
- script: List of step objects (advanced usage, 30+ step types available)
- headless: Run headless (no GUI)? default true
- browser_type: chromium / chrome / firefox / webkit
- timeout: ms, default 30000
- session_id: Reuse browser across calls

## Examples

### Navigate and extract content
run_skills("playwright", {"url": "https://example.com"})

### Take a screenshot
run_skills("playwright", {"url": "https://example.com", "action": "screenshot"})

### Custom steps (click, input, extract, etc.)
run_skills("playwright", {"func": "run", "url": "https://example.com/login", "script": [
  {"type": "input", "selector": "#user", "value": "admin"},
  {"type": "input", "selector": "#pass", "value": "123"},
  {"type": "click", "selector": "button[type=submit]"},
  {"type": "extract", "what": "all"}
]})

### Session: multiple calls, same browser
run_skills("playwright", {"func": "run", "url": "https://baidu.com", "script": [{"type": "extract", "what": "links"}], "session_id": "s1"})
run_skills("playwright", {"func": "run", "script": [{"type": "click", "selector": "a:nth-child(3)"}, {"type": "wait_for_load"}, {"type": "extract", "what": "all"}], "session_id": "s1"})
