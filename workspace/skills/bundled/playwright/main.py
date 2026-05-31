"""
Playwright浏览器自动化Skill - 支持浏览器自动化、动态网页处理、前端测试等能力
跨平台兼容版本，支持macOS、Linux、Windows系统
"""
import asyncio
import logging
import os
import sys
import platform
import subprocess
import shutil
import time
import json
import contextlib
import atexit
from typing import Dict, Any, Optional, List, Tuple, Union
from urllib.parse import urlparse
from dataclasses import dataclass, field
from enum import Enum

# ---- Session 管理（跨调用复用浏览器） ----

_SESSION_IDLE_TIMEOUT = 600


@dataclass
class _Session:
    playwright: Any
    browser: Any
    context: Any
    page: Any
    last_used: float = 0


_sessions: Dict[str, _Session] = {}
_browser_cache: Optional[List] = None  # List[BrowserInfo], defined later
_session_cleanup_task: Optional[asyncio.Task] = None  # 后台清理定时任务


def _get_cached_browsers():  # -> List[BrowserInfo], defined later
    global _browser_cache
    if _browser_cache is None:
        _browser_cache = _detect_installed_browsers()
    return _browser_cache


async def _get_session(session_id: str, headless=False, browser_type="chromium", timeout=30000):
    _ensure_cleanup_task()
    await _cleanup_idle_sessions()

    if session_id in _sessions:
        sess = _sessions[session_id]
        try:
            await sess.page.evaluate("1")
            sess.last_used = time.time()
            return sess
        except Exception:
            logger.info(f"Session {session_id} dead, recreating")
            await _close_session(session_id)

    from playwright.async_api import async_playwright
    p = await async_playwright().__aenter__()
    try:
        bt = BrowserType(browser_type.lower()) if isinstance(browser_type, str) else browser_type
        browser, context, page = await _launch_browser_with_fallback(p, bt, headless, detected_browsers=_browser_cache)
        page.set_default_timeout(timeout)
        page.set_default_navigation_timeout(timeout)
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
        """)
        sess = _Session(p, browser, context, page, time.time())
        _sessions[session_id] = sess
        return sess
    except Exception:
        await p.__aexit__(None, None, None)
        raise


async def _close_session(session_id: str):
    sess = _sessions.pop(session_id, None)
    if sess:
        close_ok = True
        try:
            await sess.context.close()
        except Exception as e:
            logger.warning(f"Session {session_id} context.close failed: {e}")
            close_ok = False
        try:
            await sess.browser.close()
        except Exception as e:
            logger.warning(f"Session {session_id} browser.close failed: {e}")
            close_ok = False
        try:
            await sess.playwright.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Session {session_id} playwright.__aexit__ failed: {e}")
            close_ok = False
        if not close_ok:
            logger.error(f"Session {session_id} browser may still be running (orphan process)")


async def _cleanup_idle_sessions():
    now = time.time()
    for sid in list(_sessions.keys()):
        if now - _sessions[sid].last_used > _SESSION_IDLE_TIMEOUT:
            await _close_session(sid)


async def _session_cleanup_loop():
    """后台定时清理空闲session，每 60 秒检查一次"""
    while True:
        try:
            await asyncio.sleep(60)
            await _cleanup_idle_sessions()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Session cleanup loop error: {e}")


def _ensure_cleanup_task():
    global _session_cleanup_task
    if _session_cleanup_task is None or _session_cleanup_task.done():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                _session_cleanup_task = loop.create_task(_session_cleanup_loop())
        except RuntimeError:
            pass


async def _close_all_sessions():
    for sid in list(_sessions.keys()):
        await _close_session(sid)


def _cleanup_sessions_sync():
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_close_all_sessions())
        else:
            loop.run_until_complete(_close_all_sessions())
    except RuntimeError:
        pass  # 无 event loop（测试环境），忽略
    except Exception as e:
        logger.warning(f"Session cleanup failed: {e}")


atexit.register(_cleanup_sessions_sync)


# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger("playwright_skill")


class BrowserType(Enum):
    """支持的浏览器类型"""
    CHROMIUM = "chromium"
    CHROME = "chrome"
    FIREFOX = "firefox"
    WEBKIT = "webkit"


class PlatformType(Enum):
    """操作系统类型"""
    MACOS = "macos"
    LINUX = "linux"
    WINDOWS = "windows"
    UNKNOWN = "unknown"


@dataclass
class BrowserInfo:
    """浏览器信息"""
    type: BrowserType
    executable_path: str
    version: Optional[str] = None
    installed: bool = False
    is_playwright_managed: bool = False


def _resolve_skill_path(path: str, project_path: str = "") -> str:
    """将相对路径解析到项目目录"""
    if os.path.isabs(path):
        return path
    base = project_path or os.environ.get("AACODE_WORK_DIR") or os.getcwd()
    return os.path.join(base, path)


def _default_screenshot_path() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join("screenshots", f"screenshot_{ts}.png")


def _default_pdf_path() -> str:
    ts = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join("pdfs", f"output_{ts}.pdf")


@dataclass
class ExecutionState:
    """运行时状态，在 run 执行过程中传递"""
    pages: List[Any]
    active_index: int = 0
    monitored_console: List[Dict] = field(default_factory=list)
    monitored_requests: List[Dict] = field(default_factory=list)
    routes: List[Dict] = field(default_factory=list)
    step_results: List[Dict] = field(default_factory=list)
    storage_snapshot: Optional[Dict] = None
    project_path: str = ""

    @property
    def page(self):
        return self.pages[self.active_index]


@contextlib.asynccontextmanager
async def _browser_context(
    headless: bool = False,
    browser_type: str = "chromium",
    timeout: int = 30000,
    context_config: Optional[Dict] = None,
):
    """统一的浏览器生命周期管理上下文管理器"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ImportError("Playwright not installed. Run: pip install playwright")

    async with async_playwright() as p:
        browser = None
        try:
            bt = BrowserType(browser_type.lower()) if isinstance(browser_type, str) else browser_type
            browser, context, page = await _launch_browser_with_fallback(p, bt, headless, context_config, _get_cached_browsers())
            page.set_default_timeout(timeout)
            page.set_default_navigation_timeout(timeout)
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
            """)
            yield browser, context, page
        finally:
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


def _get_platform() -> PlatformType:
    """Get 当前操作系统平台"""
    system = platform.system().lower()
    if system == "darwin":
        return PlatformType.MACOS
    elif system == "linux":
        return PlatformType.LINUX
    elif system == "windows":
        return PlatformType.WINDOWS
    else:
        return PlatformType.UNKNOWN


def _get_default_browser_paths() -> Dict[BrowserType, List[str]]:
    """Get 各平台默认浏览器路径"""
    platform_type = _get_platform()
    
    paths = {
        BrowserType.CHROME: [],
        BrowserType.CHROMIUM: [],
        BrowserType.FIREFOX: [],
        BrowserType.WEBKIT: []
    }
    
    if platform_type == PlatformType.MACOS:
        paths[BrowserType.CHROME] = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary",
            "/Applications/Chromium.app/Contents/MacOS/Chromium"
        ]
        paths[BrowserType.FIREFOX] = [
            "/Applications/Firefox.app/Contents/MacOS/firefox",
            "/Applications/Firefox Developer Edition.app/Contents/MacOS/firefox"
        ]
        
    elif platform_type == PlatformType.LINUX:
        paths[BrowserType.CHROME] = [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/opt/google/chrome/google-chrome"
        ]
        paths[BrowserType.CHROMIUM] = [
            "/usr/bin/chromium-browser",
            "/usr/bin/chromium",
            "/usr/local/bin/chromium"
        ]
        paths[BrowserType.FIREFOX] = [
            "/usr/bin/firefox",
            "/usr/local/bin/firefox"
        ]
        
    elif platform_type == PlatformType.WINDOWS:
        program_files = os.environ.get("ProgramFiles", "C:\\Program Files")
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
        
        paths[BrowserType.CHROME] = [
            os.path.join(program_files, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Google\\Chrome\\Application\\chrome.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google\\Chrome\\Application\\chrome.exe")
        ]
        paths[BrowserType.CHROMIUM] = [
            os.path.join(program_files, "Chromium\\Application\\chrome.exe"),
            os.path.join(program_files_x86, "Chromium\\Application\\chrome.exe")
        ]
        paths[BrowserType.FIREFOX] = [
            os.path.join(program_files, "Mozilla Firefox\\firefox.exe"),
            os.path.join(program_files_x86, "Mozilla Firefox\\firefox.exe")
        ]
    
    return paths


def _check_command_exists(cmd: str) -> bool:
    """检查命令是否存在"""
    try:
        return shutil.which(cmd) is not None
    except:
        return False


def _get_browser_version(executable_path: str) -> Optional[str]:
    """Get 浏览器版本"""
    try:
        if _get_platform() == PlatformType.WINDOWS:
            # Windows使 with wmicGet 版本
            result = subprocess.run(
                ["wmic", "datafile", "where", f"name='{executable_path.replace('/', '\\\\')}'", "get", "Version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if len(lines) > 1:
                    return lines[1].strip()
        else:
            # macOS/Linux使 with --version参数
            result = subprocess.run(
                [executable_path, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 提取版本号
                import re
                version_match = re.search(r'(\d+\.\d+\.\d+\.\d+|\d+\.\d+\.\d+)', result.stdout)
                if version_match:
                    return version_match.group(1)
    except Exception as e:
        logger.debug(f"Failed to get browser version {executable_path}: {e}")
    
    return None


def _detect_installed_browsers() -> List[BrowserInfo]:
    """检测系统已安装的浏览器"""
    browsers = []
    default_paths = _get_default_browser_paths()
    
    # 检查Playwright管理的浏览器
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_path = compute_driver_executable()
        if driver_path and os.path.exists(str(driver_path)):
            # Playwright安装的浏览器在特定目录
            playwright_dir = os.path.dirname(os.path.dirname(str(driver_path)))
            for browser_type in BrowserType:
                browser_dir = os.path.join(playwright_dir, ".local-browsers", browser_type.value)
                if os.path.exists(browser_dir):
                    # 查找可执行文件
                    for root, dirs, files in os.walk(browser_dir):
                        for file in files:
                            if file.endswith(('.exe', '')) and browser_type.value in file.lower():
                                exe_path = os.path.join(root, file)
                                browsers.append(BrowserInfo(
                                    type=browser_type,
                                    executable_path=exe_path,
                                    is_playwright_managed=True
                                ))
    except (ImportError, Exception):
        pass
    
    # 检查系统安装的浏览器
    for browser_type, paths in default_paths.items():
        for path in paths:
            if os.path.exists(path):
                version = _get_browser_version(path)
                browsers.append(BrowserInfo(
                    type=browser_type,
                    executable_path=path,
                    version=version,
                    installed=True,
                    is_playwright_managed=False
                ))
                break  # 找到第一个即可
    
    # 检查PATH中的浏览器
    browser_commands = {
        "google-chrome": BrowserType.CHROME,
        "chrome": BrowserType.CHROME,
        "chromium": BrowserType.CHROMIUM,
        "chromium-browser": BrowserType.CHROMIUM,
        "firefox": BrowserType.FIREFOX
    }
    
    for cmd, browser_type in browser_commands.items():
        if _check_command_exists(cmd):
            exe_path = shutil.which(cmd)
            if exe_path and os.path.exists(exe_path):
                version = _get_browser_version(exe_path)
                browsers.append(BrowserInfo(
                    type=browser_type,
                    executable_path=exe_path,
                    version=version,
                    installed=True,
                    is_playwright_managed=False
                ))
    
    return browsers


def _validate_url(url: str) -> Tuple[bool, str]:
    """验证URL格式"""
    try:
        result = urlparse(url)
        if all([result.scheme, result.netloc]):
            return True, ""
        else:
            return False, "URL must include protocol and domain"
    except Exception as e:
        return False, f"URL parsing failed: {str(e)}"


def _validate_selector(selector: str) -> Tuple[bool, str]:
    """验证CSS选择器"""
    if not selector or not isinstance(selector, str):
        return False, "Selector must not be empty and must be a string"
    
    # 基本验证
    if len(selector) > 1000:
        return False, "Selector too long"
    
    # 检查危险字符
    dangerous_patterns = ["javascript:", "data:", "vbscript:"]
    for pattern in dangerous_patterns:
        if pattern in selector.lower():
            return False, f"Selector contains dangerous content: {pattern}"
    
    return True, ""


def _format_error_result(error: Exception, context: str = "") -> Dict[str, Any]:
    """格式化错误结果"""
    error_msg = str(error)
    
    # 常见错误类型映射
    error_mapping = {
        "timeout": "operation timed out",
        "not found": "element not found",
        "network": "network error",
        "permission": "permission error",
        "protocol": "protocol error"
    }
    
    error_type = "unknown"
    for key, value in error_mapping.items():
        if key in error_msg.lower():
            error_type = key
            break
    
    return {
        "success": False,
        "error": error_msg,
        "error_type": error_type,
        "context": context,
        "platform": _get_platform().value,
        "timestamp": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    }


async def _wait_for_page_ready(page, wait_for: Optional[Dict] = None):
    if not wait_for:
        return

    if "selector" in wait_for:
        await page.wait_for_selector(wait_for["selector"], timeout=wait_for.get("timeout", 30000))
    elif "network" in wait_for:
        network_type = wait_for["network"]
        if network_type == "idle":
            await page.wait_for_load_state("networkidle")
        elif network_type == "load":
            await page.wait_for_load_state("load")
    elif "function" in wait_for:
        await page.wait_for_function(wait_for["function"], timeout=wait_for.get("timeout", 30000))


def _get_browser_config(platform_type: Optional[PlatformType] = None) -> Dict[str, Any]:
    """Get 浏览器配置，根据平台自动调整"""
    if platform_type is None:
        platform_type = _get_platform()
    
    # 平台特定的 with 户代理
    user_agents = {
        PlatformType.MACOS: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        PlatformType.WINDOWS: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        PlatformType.LINUX: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    return {
        "viewport": {"width": 1280, "height": 720},
        "user_agent": user_agents.get(platform_type, user_agents[PlatformType.MACOS]),
        "ignore_https_errors": True,  # 忽略HTTPS证书错误
        "java_script_enabled": True,
        "bypass_csp": False,  # 谨慎使 with 
        "locale": "zh-CN" if platform_type == PlatformType.WINDOWS else "en-US"
    }


async def _launch_browser_with_fallback(p, browser_type: BrowserType = BrowserType.CHROMIUM, 
                                        headless: bool = False, 
                                        context_config: Optional[Dict] = None,
                                        detected_browsers=None) -> Tuple[Any, Any, Any]:
    """
    统一的浏览器启动函数，支持多种浏览器和回退机制
    """
    if detected_browsers is None:
        detected_browsers = _get_cached_browsers()
    logger.debug(f"Detected {len(detected_browsers)} available browsers")
    
    # 按优先级：首选类型(Playwright) > 首选类型(系统) > Chromium兜底
    launch_errors = []

    browser_priority = [
        (browser_type, True),
        (browser_type, False),
    ]
    if browser_type not in (BrowserType.CHROMIUM, BrowserType.CHROME):
        browser_priority += [(BrowserType.CHROMIUM, True), (BrowserType.CHROME, True)]

    for target_type, prefer_playwright in browser_priority:
        # 筛选匹配的浏览器
        matching_browsers = [
            b for b in detected_browsers 
            if b.type == target_type and b.is_playwright_managed == prefer_playwright
        ]
        
        for browser_info in matching_browsers:
            try:
                logger.debug(f"Attempting to launch {target_type.value} browser (Playwright managed: {prefer_playwright})")
                
                # 根据浏览器类型选择启动方法
                launch_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ]
                if _get_platform() == PlatformType.LINUX:
                    launch_args.append("--no-sandbox")

                if target_type == BrowserType.CHROMIUM:
                    browser = await p.chromium.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None,
                        args=launch_args,
                    )
                elif target_type == BrowserType.CHROME:
                    browser = await p.chromium.launch(
                        headless=headless,
                        channel="chrome",
                        executable_path=browser_info.executable_path if not prefer_playwright else None,
                        args=launch_args,
                    )
                elif target_type == BrowserType.FIREFOX:
                    browser = await p.firefox.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None
                    )
                elif target_type == BrowserType.WEBKIT:
                    browser = await p.webkit.launch(
                        headless=headless,
                        executable_path=browser_info.executable_path if not prefer_playwright else None
                    )
                else:
                    continue
                
                # 创建上下文和页面
                config = context_config or _get_browser_config()
                context = await browser.new_context(**config)
                page = await context.new_page()
                
                logger.debug(f"Successfully launched {target_type.value} browser")
                return browser, context, page

            except Exception as e:
                error_msg = f"Failed to launch {target_type.value}: {str(e)}"
                launch_errors.append(error_msg)
                logger.warning(error_msg)
                continue
    
    # 如果所有尝试都失败，尝试使 with Playwright的默认安装
    try:
        logger.debug("Attempting to use Playwright default installation")
        browser = await p.chromium.launch(headless=headless)
        config = context_config or _get_browser_config()
        context = await browser.new_context(**config)
        page = await context.new_page()
        logger.debug("Successfully launched browser with Playwright default installation")
        return browser, context, page
    except Exception as e:
        launch_errors.append(f"Playwright default installation failed: {str(e)}")
    
    # 生成详细的错误信息
    error_details = "\n".join(launch_errors)
    platform_info = _get_platform().value
    browsers_found = [f"{b.type.value} ({'Playwright' if b.is_playwright_managed else 'System'})" 
                     for b in detected_browsers]
    
    raise RuntimeError(
        f"Unable to launch any browser.\n"
        f"Platform: {platform_info}\n"
        f"Detected browsers: {', '.join(browsers_found) if browsers_found else 'None'}\n"
        f"Error details:\n{error_details}\n"
        f"Please run the following commands to install browsers:\n"
        f"  pip install playwright\n"
        f"  playwright install chromium chrome firefox"
    )


async def _launch_browser(p, headless: bool = False, context_config: Optional[Dict] = None):
    """向后兼容的浏览器启动函数"""
    return await _launch_browser_with_fallback(p, BrowserType.CHROMIUM, headless, context_config)


_MONITOR_BUFFER_MAX = 5000
_CAPTCHA_KEYWORDS = ["验证", "captcha", "security check", "verify", "安全验证", "访问异常"]


def _is_captcha_page(title: str = "", text: str = "") -> bool:
    """检测页面是否为验证码/反爬页面"""
    combined = (title + " " + text).lower()
    for kw in _CAPTCHA_KEYWORDS:
        if kw.lower() in combined:
            return True
    return False


# ============================================================
# Step handlers for run
# ============================================================

_STEP_HANDLERS: Dict[str, Any] = {}


def _register_step(type_name: str):
    def decorator(func):
        _STEP_HANDLERS[type_name] = func
        return func
    return decorator


async def _execute_step(page, context, browser, state: ExecutionState, step: Dict) -> Dict:
    step_type = step.get("type", "")
    handler = _STEP_HANDLERS.get(step_type)
    if handler is None:
        return {"success": False, "type": step_type, "error": f"Unknown step type: {step_type}"}
    try:
        return await handler(page, context, browser, state, step)
    except Exception as e:
        return {"success": False, "type": step_type, "error": str(e)}


@_register_step("goto")
async def _step_goto(page, context, browser, state, step):
    url = step.get("value") or step.get("url") or ""
    wait_until = step.get("wait_until", "domcontentloaded")
    await page.goto(url, wait_until=wait_until)
    return {"success": True, "type": "goto", "url": page.url, "title": await page.title()}


@_register_step("click")
async def _step_click(page, context, browser, state, step):
    selector = step["selector"]
    opts = step.get("options", {})
    await page.click(selector, **opts)
    return {"success": True, "type": "click", "selector": selector}


@_register_step("input")
async def _step_input(page, context, browser, state, step):
    selector = step["selector"]
    value = str(step.get("value", ""))
    opts = step.get("options", {})
    await page.fill(selector, value, **opts)
    return {"success": True, "type": "input", "selector": selector, "value": value}


@_register_step("type")
async def _step_type(page, context, browser, state, step):
    selector = step["selector"]
    value = str(step.get("value", ""))
    opts = step.get("options", {})
    await page.type(selector, value, **opts)
    return {"success": True, "type": "type", "selector": selector, "value": value}


@_register_step("select")
async def _step_select(page, context, browser, state, step):
    selector = step["selector"]
    value = step.get("value", "")
    opts = step.get("options", {})
    await page.select_option(selector, value, **opts)
    return {"success": True, "type": "select", "selector": selector, "value": value}


@_register_step("hover")
async def _step_hover(page, context, browser, state, step):
    selector = step["selector"]
    opts = step.get("options", {})
    await page.hover(selector, **opts)
    return {"success": True, "type": "hover", "selector": selector}


@_register_step("scroll")
async def _step_scroll(page, context, browser, state, step):
    selector = step.get("selector")
    value = step.get("value", 500)
    opts = step.get("options", {})
    if selector:
        await page.locator(selector).scroll_into_view_if_needed(**opts)
    else:
        await page.evaluate(f"window.scrollBy(0, {int(value)})")
    return {"success": True, "type": "scroll", "selector": selector}


@_register_step("wait")
async def _step_wait(page, context, browser, state, step):
    ms = int(step.get("value") or step.get("timeout") or 1000)
    await page.wait_for_timeout(ms)
    return {"success": True, "type": "wait", "duration_ms": ms}


@_register_step("wait_for_selector")
async def _step_wait_for_selector(page, context, browser, state, step):
    selector = step["selector"]
    timeout = step.get("timeout", 30000)
    state_ = step.get("state", "visible")
    await page.wait_for_selector(selector, timeout=timeout, state=state_)
    return {"success": True, "type": "wait_for_selector", "selector": selector}


@_register_step("wait_for_load")
async def _step_wait_for_load(page, context, browser, state, step):
    load_state = step.get("value", step.get("state", "load"))
    await page.wait_for_load_state(load_state)
    return {"success": True, "type": "wait_for_load", "state": load_state}


@_register_step("wait_for_function")
async def _step_wait_for_function(page, context, browser, state, step):
    expr = step.get("value") or step.get("expression") or step.get("js") or ""
    timeout = step.get("timeout", 30000)
    if not expr:
        return {"success": False, "type": "wait_for_function", "error": "No expression provided"}
    await page.wait_for_function(expr, timeout=timeout)
    return {"success": True, "type": "wait_for_function", "expression": expr}


@_register_step("evaluate")
async def _step_evaluate(page, context, browser, state, step):
    expression = step.get("value") or step.get("expression") or step.get("js") or step.get("code") or step.get("script") or ""
    args = step.get("args", [])
    if not expression:
        return {"success": False, "type": "evaluate", "error": "No expression provided (try: value/expression/js/code)"}
    result = await page.evaluate(expression, *args)
    serializable = isinstance(result, (str, int, float, bool, list, dict, type(None)))
    return {
        "success": True,
        "type": "evaluate",
        "result": result if serializable else str(result),
    }


@_register_step("back")
async def _step_back(page, context, browser, state, step):
    await page.go_back()
    return {"success": True, "type": "back", "url": page.url}


@_register_step("forward")
async def _step_forward(page, context, browser, state, step):
    await page.go_forward()
    return {"success": True, "type": "forward", "url": page.url}


@_register_step("screenshot")
async def _step_screenshot(page, context, browser, state, step):
    path = _resolve_skill_path(step.get("path") or _default_screenshot_path(), state.project_path)
    full_page = step.get("full_page", False)
    selector = step.get("selector")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if selector:
        element = await page.query_selector(selector)
        if element:
            await element.screenshot(path=path)
        else:
            await page.screenshot(path=path, full_page=full_page)
    else:
        await page.screenshot(path=path, full_page=full_page)
    file_size = os.path.getsize(path) if os.path.exists(path) else 0
    return {
        "success": os.path.exists(path),
        "type": "screenshot",
        "path": path,
        "full_page": full_page,
        "selector": selector,
        "file_size": file_size,
    }


@_register_step("pdf")
async def _step_pdf(page, context, browser, state, step):
    path = _resolve_skill_path(step.get("path") or _default_pdf_path(), state.project_path)
    opts = step.get("options", {})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    await page.pdf(path=path, **opts)
    file_size = os.path.getsize(path) if os.path.exists(path) else 0
    return {"success": True, "type": "pdf", "path": path, "file_size": file_size}


@_register_step("extract")
async def _step_extract(page, context, browser, state, step):
    what = step.get("what", "text")
    data = None

    if what == "text":
        data = await page.evaluate("() => document.body?.innerText?.trim() || ''")
    elif what == "html":
        data = await page.content()
    elif what == "links":
        data = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({text: a.innerText.trim(), href: a.href}))
                .filter(l => l.href)
        """)
    elif what == "images":
        data = await page.evaluate("""
            () => Array.from(document.querySelectorAll('img[src]'))
                .map(img => ({src: img.src, alt: img.alt || ''}))
                .filter(i => i.src)
        """)
    elif what == "table":
        data = await page.evaluate("""
            () => Array.from(document.querySelectorAll('table')).map(table =>
                Array.from(table.querySelectorAll('tr')).map(row =>
                    Array.from(row.querySelectorAll('th, td')).map(c => c.innerText.trim())
                )
            )
        """)
    elif what == "title":
        data = await page.title()
    elif what == "metadata":
        data = await page.evaluate("""
            () => {
                const meta = {};
                document.querySelectorAll('meta').forEach(m => {
                    if (m.name) meta[m.name] = m.content;
                    if (m.getAttribute('property')) meta[m.getAttribute('property')] = m.content;
                });
                return meta;
            }
        """)
    elif what == "markdown":
        data = await page.evaluate("() => document.body?.innerText?.trim() || ''")
    elif what == "all":
        title = await page.title()
        text = await page.evaluate("() => document.body?.innerText?.trim() || ''")
        links = await page.evaluate("""
            () => Array.from(document.querySelectorAll('a[href]'))
                .map(a => ({text: a.innerText.trim(), href: a.href}))
                .filter(l => l.href)
        """)
        metadata = await page.evaluate("""
            () => {
                const meta = {};
                document.querySelectorAll('meta').forEach(m => {
                    if (m.name) meta[m.name] = m.content;
                    if (m.getAttribute('property')) meta[m.getAttribute('property')] = m.content;
                });
                return meta;
            }
        """)
        data = {"title": title, "text": text, "links": links, "metadata": metadata}

    return {"success": True, "type": "extract", "what": what, "data": data}


@_register_step("set_viewport")
async def _step_set_viewport(page, context, browser, state, step):
    width = step.get("width", 1280)
    height = step.get("height", 720)
    await page.set_viewport_size({"width": width, "height": height})
    return {"success": True, "type": "set_viewport", "width": width, "height": height}


@_register_step("keyboard")
async def _step_keyboard(page, context, browser, state, step):
    action = step.get("action", "press")
    key = step.get("key", step.get("value", ""))
    if action == "press":
        await page.keyboard.press(key)
    elif action == "type":
        await page.keyboard.type(key)
    elif action == "down":
        await page.keyboard.down(key)
    elif action == "up":
        await page.keyboard.up(key)
    return {"success": True, "type": "keyboard", "action": action, "key": key}


@_register_step("mouse")
async def _step_mouse(page, context, browser, state, step):
    action = step.get("action", "click")
    x = step.get("x", 0)
    y = step.get("y", 0)
    opts = step.get("options", {})
    if action == "click":
        if step.get("selector"):
            await page.click(step["selector"], **opts)
        else:
            await page.mouse.click(x, y, **opts)
    elif action == "move":
        await page.mouse.move(x, y, **opts)
    elif action == "down":
        await page.mouse.down(**opts)
    elif action == "up":
        await page.mouse.up(**opts)
    elif action == "dblclick":
        await page.mouse.dblclick(x, y, **opts)
    return {"success": True, "type": "mouse", "action": action, "x": x, "y": y}


@_register_step("add_script")
async def _step_add_script(page, context, browser, state, step):
    content = step.get("content", "")
    script_url = step.get("url")
    if script_url:
        await page.add_init_script(path=script_url)
    else:
        await page.add_init_script(content)
    return {"success": True, "type": "add_script"}


@_register_step("inject_cookie")
async def _step_inject_cookie(page, context, browser, state, step):
    cookies = step.get("cookies", [])
    if not cookies and step.get("name"):
        cookies = [{"name": step["name"], "value": step.get("value", ""), "url": step.get("url", page.url)}]
    await context.add_cookies(cookies)
    return {"success": True, "type": "inject_cookie", "count": len(cookies)}


@_register_step("route")
async def _step_route(page, context, browser, state, step):
    pattern = step.get("pattern", "**/*")
    handler_type = step.get("handler", "abort")
    if handler_type == "abort":
        await page.route(pattern, lambda route: route.abort())
    elif handler_type == "continue":
        await page.route(pattern, lambda route: route.continue_())
    elif handler_type == "fulfill" and step.get("body"):
        await page.route(pattern, lambda route: route.fulfill(
            body=step.get("body", ""),
            content_type=step.get("content_type", "text/plain"),
            status=step.get("status", 200),
        ))
    return {"success": True, "type": "route", "pattern": pattern, "handler": handler_type}


@_register_step("console_monitor")
async def _step_console_monitor(page, context, browser, state, step):
    events = set(step.get("events", ["log", "error"]))

    if not hasattr(page, "_console_buffer"):
        page._console_buffer = []

        async def _on_console(msg):
            if len(page._console_buffer) >= _MONITOR_BUFFER_MAX:
                page._console_buffer.pop(0)
            page._console_buffer.append({
                "type": msg.type,
                "text": msg.text,
                "location": str(msg.location) if hasattr(msg, 'location') else "",
            })

        page.on("console", _on_console)

    state.monitored_console = [m for m in page._console_buffer if m["type"] in events]
    return {"success": True, "type": "console_monitor", "monitoring": list(events)}


@_register_step("request_monitor")
async def _step_request_monitor(page, context, browser, state, step):
    patterns = step.get("patterns", ["**/*"])

    if not hasattr(page, "_request_buffer"):
        page._request_buffer = []

        async def _on_request(request):
            if len(page._request_buffer) >= _MONITOR_BUFFER_MAX:
                page._request_buffer.pop(0)
            page._request_buffer.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "headers": dict(request.headers),
            })

        page.on("request", _on_request)

    import fnmatch
    state.monitored_requests = [r for r in page._request_buffer if any(fnmatch.fnmatch(r["url"], p) for p in patterns)]
    return {"success": True, "type": "request_monitor", "patterns": patterns}


@_register_step("new_page")
async def _step_new_page(page, context, browser, state, step):
    new_page = await context.new_page()
    new_page.set_default_timeout(step.get("timeout", 30000))
    await new_page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    """)
    url = step.get("url", step.get("value"))
    if url:
        await new_page.goto(url, wait_until="domcontentloaded")
    state.pages.append(new_page)
    state.active_index = len(state.pages) - 1
    return {"success": True, "type": "new_page", "url": url or "about:blank", "page_index": state.active_index}


@_register_step("switch_page")
async def _step_switch_page(page, context, browser, state, step):
    index = step.get("value", step.get("index", 0))
    if index < 0 or index >= len(state.pages):
        return {"success": False, "type": "switch_page", "error": f"Page index {index} out of range (0-{len(state.pages) - 1})"}
    state.active_index = index
    return {"success": True, "type": "switch_page", "page_index": index, "url": state.page.url}


@_register_step("close_page")
async def _step_close_page(page, context, browser, state, step):
    if len(state.pages) <= 1:
        return {"success": False, "type": "close_page", "error": "Cannot close the last page"}
    closed_index = state.active_index
    await state.page.close()
    state.pages.pop(closed_index)
    state.active_index = max(0, closed_index - 1)
    return {"success": True, "type": "close_page", "closed_index": closed_index}


# --- Extra step types ---

@_register_step("reload")
async def _step_reload(page, context, browser, state, step):
    cache_bypass = step.get("cache", step.get("hard", False))
    if cache_bypass:
        await context.add_cookies([{"name": "_cache_buster", "value": str(time.time()), "url": page.url}])
    await page.reload(wait_until=step.get("wait_until", "domcontentloaded"))
    return {"success": True, "type": "reload", "url": page.url, "cache_bypass": cache_bypass}


@_register_step("file_upload")
async def _step_file_upload(page, context, browser, state, step):
    selector = step["selector"]
    files = step.get("files", step.get("value"))
    if isinstance(files, str):
        files = [files]
    await page.set_input_files(selector, files)
    return {"success": True, "type": "file_upload", "selector": selector, "files": files}


@_register_step("dialog")
async def _step_dialog(page, context, browser, state, step):
    action = step.get("action", "accept")
    text = step.get("value", step.get("text"))

    if not hasattr(page, "_dialog_handler_set"):
        async def handler(dialog):
            s = getattr(page, "_current_dialog_state", None)
            if s is not None:
                s.monitored_console.append({"type": "dialog", "message": dialog.message, "default_value": dialog.default_value})
            act = getattr(page, "_dialog_action", "accept")
            txt = getattr(page, "_dialog_text", None)
            if act == "accept" and txt:
                await dialog.accept(txt)
            elif act == "accept":
                await dialog.accept()
            else:
                await dialog.dismiss()

        page._dialog_handler_set = True
        page.on("dialog", handler)

    page._current_dialog_state = state
    page._dialog_action = action
    page._dialog_text = text
    return {"success": True, "type": "dialog", "action": action}


@_register_step("check")
async def _step_check(page, context, browser, state, step):
    selector = step["selector"]
    opts = step.get("options", {})
    await page.check(selector, **opts)
    return {"success": True, "type": "check", "selector": selector}


@_register_step("uncheck")
async def _step_uncheck(page, context, browser, state, step):
    selector = step["selector"]
    opts = step.get("options", {})
    await page.uncheck(selector, **opts)
    return {"success": True, "type": "uncheck", "selector": selector}


@_register_step("drag_and_drop")
async def _step_drag_and_drop(page, context, browser, state, step):
    source = step["source"]
    target = step.get("target")
    x = step.get("x")
    y = step.get("y")
    if target:
        await page.drag_and_drop(source, target)
    elif x is not None and y is not None:
        source_el = page.locator(source)
        await source_el.drag_to(page.locator("body"), target_position={"x": x, "y": y})
    return {"success": True, "type": "drag_and_drop", "source": source}


@_register_step("storage_state")
async def _step_storage_state(page, context, browser, state, step):
    action = step.get("action", "save")
    if action == "save":
        storage = await context.storage_state()
        state.storage_snapshot = storage
        return {"success": True, "type": "storage_state", "action": "save", "cookies_count": len(storage.get("cookies", [])), "origins_count": len(storage.get("origins", []))}
    elif action == "load":
        data = step.get("data") or state.storage_snapshot
        if data and data.get("cookies"):
            await context.add_cookies(data["cookies"])
            return {"success": True, "type": "storage_state", "action": "load", "cookies_restored": len(data["cookies"])}
    return {"success": False, "type": "storage_state", "error": "No storage data available"}


@_register_step("frame")
async def _step_frame(page, context, browser, state, step):
    selector = step["selector"]
    sub_steps = step.get("steps", [])
    frame = page.frame_locator(selector)
    results = []
    for sub in sub_steps:
        sub_type = sub.get("type", "")
        r = {"type": sub_type, "success": True}
        if sub_type == "click":
            await frame.locator(sub["selector"]).click(**sub.get("options", {}))
        elif sub_type == "input":
            await frame.locator(sub["selector"]).fill(str(sub.get("value", "")), **sub.get("options", {}))
        elif sub_type == "type":
            await frame.locator(sub["selector"]).type(str(sub.get("value", "")), **sub.get("options", {}))
        elif sub_type == "select":
            await frame.locator(sub["selector"]).select_option(sub.get("value", ""), **sub.get("options", {}))
        elif sub_type == "wait":
            await page.wait_for_timeout(int(sub.get("value", 1000)))
        elif sub_type == "evaluate":
            r["result"] = await frame.owner().evaluate(sub.get("value", ""))
        else:
            r["success"] = False
            r["error"] = f"Unknown frame sub-step: {sub_type}"
        results.append(r)
    return {"success": True, "type": "frame", "selector": selector, "sub_results": results}


@_register_step("performance")
async def _step_performance(page, context, browser, state, step):
    metrics = await page.metrics()
    timing = await page.evaluate("() => JSON.stringify(window.performance.timing)")
    return {"success": True, "type": "performance", "metrics": metrics, "timing": timing}


@_register_step("close_session")
async def _step_close_session(page, context, browser, state, step):
    session_id = step.get("session_id", step.get("value", ""))
    if session_id:
        await _close_session(session_id)
        return {"success": True, "type": "close_session", "session_id": session_id}
    return {"success": False, "type": "close_session", "error": "No session_id provided"}


# ============================================================
# run - Unified Playwright script execution engine (primary entry)
# ============================================================


async def _get_page_title(state: ExecutionState) -> str:
    try:
        return await state.page.title() if state.pages else ""
    except Exception:
        return ""


def _get_extracted_text(state: ExecutionState) -> str:
    """从步骤结果中提取页面文本，用于 CAPTCHA 检测"""
    for s in state.step_results:
        if s.get("type") != "extract":
            continue
        d = s.get("data")
        if isinstance(d, str):
            return d
        if isinstance(d, dict):
            text = d.get("text") or d.get("preview") or ""
            if text:
                return text
    return ""


def _build_result(success: bool, **kw) -> Dict:
    return {
        "success": success,
        "url": kw.get("url", ""),
        "title": kw.get("title", ""),
        "steps": kw.get("steps", []),
        "browser_info": {"type": kw.get("browser_type"), "headless": kw.get("headless"), "platform": _get_platform().value},
        "platform": _get_platform().value,
        "duration_ms": (time.time() - kw.get("start_time", time.time())) * 1000,
        "error": kw.get("error"),
        "error_type": kw.get("error_type"),
        "captcha_detected": kw.get("captcha_detected", False),
        "monitored_console": kw.get("monitored_console", []),
        "monitored_requests": kw.get("monitored_requests", []),
        **({"session_id": kw["session_id"]} if "session_id" in kw else {}),
    }


async def run(
    script: Optional[List[Dict[str, Any]]] = None,
    url: Optional[str] = None,
    action: Optional[str] = None,
    headless: bool = True,
    browser_type: str = "chromium",
    timeout: int = 30000,
    retry_count: int = 2,
    retry_delay: float = 1.0,
    context_config: Optional[Dict] = None,
    session_id: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    统一的 Playwright 脚本执行引擎。

    Args:
        script: 步骤列表，每个步骤是一个 dict，必须包含 "type" 字段
        url: 可选的初始导航 URL
        action: 快捷操作 (navigate/scrape/screenshot), 自动生成 script
        headless: 是否无头模式，默认 False (显示浏览器窗口)
        browser_type: 浏览器类型 (chromium, chrome, firefox, webkit)
        timeout: 超时时间(毫秒)
        retry_delay: 重试延迟(秒)
        session_id: 会话 ID，提供后可跨调用复用同一浏览器

    Returns:
        {
            "success": bool,
            "url": str,
            "title": str,
            "session_id": str,  # 会话 ID（当使用 session 时）
            "steps": List[Dict],
            "browser_info": Dict,
            "platform": str,
            "duration_ms": float,
            "error": Optional[str],
            "captcha_detected": bool,
        }
    """
    start_time = time.time()
    _ensure_cleanup_task()
    await _cleanup_idle_sessions()

    if not script:
        script = []
    if action == "screenshot":
        if not any(s.get("type") == "screenshot" for s in script):
            script.append({"type": "screenshot", "full_page": True})
    elif action != "none" and not any(s.get("type") in ("extract", "screenshot", "pdf") for s in script):
        script.append({"type": "extract", "what": "all"})

    if not script and not url:
        return {"success": False, "error": "Provide url or script to do something", "duration_ms": 0, "platform": _get_platform().value}

    for attempt in range(retry_count + 1):
        cm = None
        try:
            if session_id:
                sess = await _get_session(session_id, headless, browser_type, timeout)
                browser, context, page = sess.browser, sess.context, sess.page
            else:
                cm = _browser_context(headless, browser_type, timeout, context_config)
                browser, context, page = await cm.__aenter__()

            state = ExecutionState(pages=[page], project_path=kwargs.get("_project_path", ""))
            if url:
                await page.goto(url, wait_until="domcontentloaded")

            for i, step in enumerate(script):
                step_start = time.time()
                result = await _execute_step(page, context, browser, state, step)
                result["duration_ms"] = (time.time() - step_start) * 1000
                result["step_index"] = i
                state.step_results.append(result)
                if not result.get("success", True) and step.get("abort_on_error", True):
                    break

            title = await _get_page_title(state)
            overall_success = all(r.get("success", True) for r in state.step_results)
            step_errors = [s.get("error") for s in state.step_results if not s.get("success") and s.get("error")]
            first_error = step_errors[0] if step_errors else (None if overall_success else "Unknown step error")
            page_text = _get_extracted_text(state)
            is_captcha = _is_captcha_page(title=title, text=page_text)

            if session_id and session_id in _sessions:
                _sessions[session_id].page = state.page
                _sessions[session_id].last_used = time.time()

            if is_captcha:
                logger.warning("CAPTCHA detected, returning for model to decide next step")
                return _build_result(True,
                    url=url or (state.page.url if state.pages else ""), title=title,
                    steps=state.step_results, browser_type=browser_type, headless=headless,
                    start_time=start_time,
                    error="CAPTCHA detected",
                    error_type="captcha", captcha_detected=True,
                    monitored_console=state.monitored_console, monitored_requests=state.monitored_requests,
                    **({"session_id": session_id} if session_id else {}))

            return _build_result(overall_success,
                url=url or (state.page.url if state.pages else ""), title=title,
                steps=state.step_results, browser_type=browser_type, headless=headless,
                start_time=start_time,
                error=first_error or ("CAPTCHA detected" if is_captcha else None),
                error_type="captcha" if is_captcha else None, captcha_detected=is_captcha,
                monitored_console=state.monitored_console, monitored_requests=state.monitored_requests,
                **({"session_id": session_id} if session_id else {}))

        except ImportError:
            return {"success": False, "error": "Playwright not installed", "error_type": "import_error", "steps": [], "duration_ms": (time.time() - start_time) * 1000, "platform": _get_platform().value, "solution": "pip install playwright && playwright install chromium chrome firefox"}
        except Exception as e:
            if attempt < retry_count:
                await asyncio.sleep(retry_delay)
                continue
            err = _format_error_result(e, "run failed")
            err.update({"duration_ms": (time.time() - start_time) * 1000, **({"session_id": session_id} if session_id else {})})
            return err
        finally:
            if cm:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass

    return {"success": False, "error": f"All {retry_count + 1} attempts failed", "error_type": "max_retries_exceeded", "steps": [], "duration_ms": (time.time() - start_time) * 1000, "retry_attempts": retry_count, "platform": _get_platform().value}


async def browser_automation(
    url: str,
    steps: Optional[List[Dict[str, Any]]] = None,
    action: Optional[str] = None,
    wait_for: Optional[Dict[str, Any]] = None,
    extract: Optional[List[str]] = None,
    screenshot: Optional[Dict[str, Any]] = None,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    retry_delay: float = 1.0,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    浏览器自动化操作 - 支持动态网页处理和数据提取

    Args:
        url: 目标URL
        action: 快捷操作 (navigate/scrape/screenshot), 自动生成 script
        steps: 操作步骤列表，每项包含:
            - type: 操作类型 (click, input, select, hover, scroll, wait, evaluate, goto, back, forward)
            - selector: CSS选择器
            - value: 输入值/选项值
            - options: 额外选项
        wait_for: 等待条件
        extract: 提取数据类型列表
        screenshot: 截图配置
        timeout: 超时时间(毫秒)，默认30000
        headless: 是否无头模式，默认True
        browser_type: 浏览器类型
        retry_count: 重试次数，默认2
        retry_delay: 重试延迟(秒)，默认1.0

    Returns:
        操作结果
    """
    start_time = time.time()
    logger.info(f"browser_automation starting: {url}")

    # 快捷 action 模式：只要没有显式传 steps/extract/screenshot，就自动提取
    if not steps and not extract and not screenshot:
        if action == "screenshot":
            result = await run(url=url, action="screenshot", headless=headless, browser_type=browser_type, timeout=timeout, retry_count=retry_count)
        else:
            result = await run(url=url, headless=headless, browser_type=browser_type, timeout=timeout, retry_count=retry_count)
        return {
            "success": result["success"],
            "url": url,
            "title": result.get("title", ""),
            "actions_performed": result.get("steps", []),
            "extracted_data": {s.get("what", "all"): s.get("data") for s in (result.get("steps") or []) if s.get("type") == "extract"},
            "screenshot": None,
            "browser_info": result.get("browser_info", {}),
            "platform": result.get("platform", _get_platform().value),
            "duration": result.get("duration_ms", 0) / 1000,
            "error": result.get("error"),
            "error_type": result.get("error_type"),
            "retry_attempts": result.get("retry_attempts", 0),
        }

    validation_errors = []

    url_valid, url_error = _validate_url(url)
    if not url_valid:
        validation_errors.append(f"URL validation failed: {url_error}")

    if steps:
        if not isinstance(steps, list):
            validation_errors.append("steps must be a list")
        else:
            for i, s in enumerate(steps):
                if not isinstance(s, dict):
                    validation_errors.append(f"steps[{i}] must be a dict")
                elif "type" not in s:
                    validation_errors.append(f"steps[{i}] missing 'type' field (use e.g. {{\"type\": \"click\", \"selector\": \"...\"}})")
                elif s.get("selector"):
                    sv, se = _validate_selector(s["selector"])
                    if not sv:
                        validation_errors.append(f"steps[{i}] selector invalid: {se}")

    if extract:
        if not isinstance(extract, list):
            validation_errors.append("extract must be a list")
        else:
            valid_extract_types = {"text", "html", "links", "images", "table", "title", "metadata", "all"}
            for et in extract:
                if et not in valid_extract_types:
                    validation_errors.append(f"Unsupported extract type: {et}")

    if not isinstance(timeout, int) or timeout < 1000 or timeout > 300000:
        validation_errors.append("timeout must be between 1000-300000ms")

    valid_browser_types = {"chromium", "chrome", "firefox", "webkit"}
    if browser_type.lower() not in valid_browser_types:
        validation_errors.append(f"Unsupported browser_type: {browser_type}")

    if validation_errors:
        return {
            "success": False,
            "url": url,
            "error": "Parameter validation failed",
            "validation_errors": validation_errors,
            "platform": _get_platform().value
        }

    browser_type_enum = BrowserType(browser_type.lower())

    for attempt in range(retry_count + 1):
        try:
            async with _browser_context(headless, browser_type, timeout) as (browser, context, page):
                result = {
                    "success": True,
                    "url": url,
                    "title": "",
                    "actions_performed": [],
                    "extracted_data": {},
                    "screenshot": None,
                    "browser_info": {
                        "type": browser_type,
                        "headless": headless,
                        "platform": _get_platform().value,
                    },
                    "platform": _get_platform().value,
                    "duration": 0,
                    "error": None,
                    "error_type": None,
                    "retry_attempts": 0,
                }

                detected_browsers = _get_cached_browsers()
                matching_browsers = [b for b in detected_browsers if b.type == browser_type_enum]
                if matching_browsers:
                    result["browser_info"]["detected_version"] = matching_browsers[0].version
                    result["browser_info"]["is_playwright_managed"] = matching_browsers[0].is_playwright_managed

                nav_start = time.time()
                await page.goto(url, wait_until="domcontentloaded")
                result["actions_performed"].append({
                    "type": "goto",
                    "url": url,
                    "duration": time.time() - nav_start,
                })

                result["title"] = await page.title()

                if wait_for:
                    await _wait_for_page_ready(page, wait_for)

                if steps:
                    for step in steps:
                        act_start = time.time()
                        action_result = await _execute_action(page, step)
                        action_result["duration"] = time.time() - act_start
                        result["actions_performed"].append(action_result)

                await page.wait_for_load_state("load")

                if extract:
                    for et in extract:
                        data = await _extract_data(page, et)
                        result["extracted_data"][et] = data

                if screenshot:
                    _proj = kwargs.get("_project_path", "")
                    sp = _resolve_skill_path(screenshot.get("path") or _default_screenshot_path(), _proj)
                    full_page = screenshot.get("full_page", False)
                    sel = screenshot.get("selector")
                    os.makedirs(os.path.dirname(sp) or ".", exist_ok=True)
                    if sel:
                        element = await page.query_selector(sel)
                        if element:
                            await element.screenshot(path=sp)
                        else:
                            logger.warning(f"Screenshot element not found: {sel}")
                            await page.screenshot(path=sp, full_page=full_page)
                    else:
                        await page.screenshot(path=sp, full_page=full_page)
                    result["screenshot"] = {
                        "path": sp,
                        "full_page": full_page,
                        "selector": sel,
                        "file_size": os.path.getsize(sp) if os.path.exists(sp) else 0,
                    }
                    result["actions_performed"].append({"type": "screenshot", "path": sp})

                result["duration"] = time.time() - start_time
                result["retry_attempts"] = attempt
                return result

        except ImportError:
            return {
                "success": False,
                "url": url,
                "error": "Playwright not installed",
                "error_type": "import_error",
                "platform": _get_platform().value,
                "solution": "pip install playwright && playwright install chromium chrome firefox",
            }
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay}s: {str(e)}")
                await asyncio.sleep(retry_delay)
                continue
            error_result = _format_error_result(e, "Browser automation failed")
            error_result.update({
                "url": url,
                "retry_attempts": attempt,
                "duration": time.time() - start_time,
            })
            return error_result

    return {
        "success": False,
        "url": url,
        "error": f"All {retry_count + 1} attempts failed",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": time.time() - start_time,
    }


async def _handle_wait(page, wait_config: Dict[str, Any]):
    """处理等待条件"""
    if "selector" in wait_config:
        await page.wait_for_selector(wait_config["selector"], timeout=wait_config.get("timeout", 30000))
    elif "network" in wait_config:
        network_type = wait_config["network"]
        if network_type == "idle":
            await page.wait_for_load_state("networkidle")
        elif network_type == "slow":
            await page.wait_for_load_state("networkidle", timeout=60000)


async def _execute_action(page, action: Dict[str, Any]) -> Dict[str, Any]:
    """执行单个操作"""
    action_type = action.get("type", "")
    selector = action.get("selector", "")
    value = action.get("value", "")
    options = action.get("options", {})
    
    result = {"type": action_type, "selector": selector}
    
    try:
        if action_type == "click":
            await page.click(selector, **options)
            result["status"] = "success"
            
        elif action_type == "input":
            await page.fill(selector, str(value), **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "type":
            await page.type(selector, str(value), **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "select":
            await page.select_option(selector, value, **options)
            result["status"] = "success"
            result["value"] = value
            
        elif action_type == "hover":
            await page.hover(selector, **options)
            result["status"] = "success"
            
        elif action_type == "scroll":
            if selector:
                await page.locator(selector).scroll_into_view_if_needed(**options)
            else:
                await page.evaluate(f"window.scrollBy(0, {value or 500})")
            result["status"] = "success"
            
        elif action_type == "wait":
            await page.wait_for_timeout(int(value) if value else 1000)
            result["status"] = "success"
            
        elif action_type == "evaluate":
            js_result = await page.evaluate(value)
            result["status"] = "success"
            result["result"] = js_result
            
        elif action_type == "goto":
            await page.goto(value, wait_until="domcontentloaded")
            result["status"] = "success"
            
        elif action_type == "back":
            await page.go_back()
            result["status"] = "success"
            
        elif action_type == "forward":
            await page.go_forward()
            result["status"] = "success"
            
        else:
            result["status"] = "unknown_action"
            
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result


async def _extract_data(page, extract_type: str) -> Any:
    """提取页面数据"""
    try:
        if extract_type == "text":
            return await page.evaluate("""
                () => {
                    const body = document.body;
                    return body ? body.innerText.trim() : '';
                }
            """)
            
        elif extract_type == "html":
            return await page.content()
            
        elif extract_type == "links":
            return await page.evaluate("""
                () => {
                    const links = Array.from(document.querySelectorAll('a[href]'));
                    return links.map(a => ({
                        text: a.innerText.trim(),
                        href: a.href
                    })).filter(l => l.href);
                }
            """)
            
        elif extract_type == "images":
            return await page.evaluate("""
                () => {
                    const imgs = Array.from(document.querySelectorAll('img[src]'));
                    return imgs.map(img => ({
                        src: img.src,
                        alt: img.alt || ''
                    })).filter(i => i.src);
                }
            """)
            
        elif extract_type == "table":
            return await page.evaluate("""
                () => {
                    const tables = Array.from(document.querySelectorAll('table'));
                    return tables.map(table => {
                        const rows = Array.from(table.querySelectorAll('tr'));
                        return rows.map(row => {
                            const cells = Array.from(row.querySelectorAll('th, td'));
                            return cells.map(cell => cell.innerText.trim());
                        });
                    });
                }
            """)
            
        elif extract_type == "title":
            return await page.title()
            
        elif extract_type == "metadata":
            return await page.evaluate("""
                () => {
                    const meta = {};
                    document.querySelectorAll('meta').forEach(m => {
                        if (m.name) meta[m.name] = m.content;
                        if (m.getAttribute('property')) meta[m.getAttribute('property')] = m.content;
                    });
                    return meta;
                }
            """)
            
        elif extract_type == "all":
            return {
                "title": await page.title(),
                "text": await _extract_data(page, "text"),
                "links": await _extract_data(page, "links"),
                "images": await _extract_data(page, "images"),
                "metadata": await _extract_data(page, "metadata")
            }
            
    except Exception as e:
        return {"error": str(e)}
    
    return None


async def scrape_dynamic_page(
    url: str,
    selectors: Optional[List[str]] = None,
    wait_for_selector: Optional[str] = None,
    extract_text: bool = True,
    extract_links: bool = False,
    extract_tables: bool = False,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    抓取动态网页内容 - 适用于 JavaScript 渲染的页面

    Args:
        url: 目标URL
        selectors: CSS选择器列表，指定要提取的元素
        wait_for_selector: 等待元素出现后再提取
        extract_text: 是否提取文本
        extract_links: 是否提取链接
        extract_tables: 是否提取表格
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数

    Returns:
        抓取结果
    """
    start_time = time.time()
    logger.info(f"scrape_dynamic_page starting: {url}")

    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {"success": False, "url": url, "error": f"URL validation failed: {url_error}", "platform": _get_platform().value}

    if selectors:
        for i, s in enumerate(selectors):
            sv, se = _validate_selector(s)
            if not sv:
                return {"success": False, "url": url, "error": f"Selector [{i}] invalid: {se}", "platform": _get_platform().value}

    if wait_for_selector:
        sv, se = _validate_selector(wait_for_selector)
        if not sv:
            return {"success": False, "url": url, "error": f"Wait selector invalid: {se}", "platform": _get_platform().value}

    for attempt in range(retry_count + 1):
        try:
            async with _browser_context(headless, browser_type, timeout) as (browser, context, page):
                result = {
                    "success": True,
                    "url": url,
                    "title": "",
                    "content": {},
                    "platform": _get_platform().value,
                    "duration": 0,
                    "error": None,
                    "retry_attempts": 0,
                }

                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"Navigated to: {url}")

                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)

                await page.wait_for_load_state("load")

                result["title"] = await page.title()

                if extract_text:
                    result["content"]["text"] = await page.evaluate("() => document.body.innerText.trim()")

                if extract_links:
                    result["content"]["links"] = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('a[href]'))
                            .map(a => ({text: a.innerText.trim(), href: a.href}))
                            .filter(l => l.href)
                    """)

                if extract_tables:
                    result["content"]["tables"] = await page.evaluate("""
                        () => Array.from(document.querySelectorAll('table')).map(table => {
                            return Array.from(table.querySelectorAll('tr')).map(row =>
                                Array.from(row.querySelectorAll('th, td')).map(c => c.innerText.trim())
                            );
                        })
                    """)

                if selectors:
                    for sel in selectors:
                        safe_sel = sel.replace("'", "\\'").replace('"', '\\"')
                        result["content"][f"selector_{sel}"] = await page.evaluate(f"""
                            () => {{
                                try {{
                                    const els = document.querySelectorAll('{safe_sel}');
                                    return Array.from(els).map(el => ({{
                                        text: el.innerText.trim(),
                                        html: el.innerHTML,
                                        tag: el.tagName.toLowerCase(),
                                        id: el.id || '',
                                        class: el.className || ''
                                    }}));
                                }} catch (e) {{
                                    return {{error: e.toString()}};
                                }}
                            }}
                        """)

                result["retry_attempts"] = attempt
                result["duration"] = time.time() - start_time
                return result

        except ImportError:
            return {"success": False, "url": url, "error": "Playwright not installed", "error_type": "import_error", "platform": _get_platform().value}
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                await asyncio.sleep(1)
                continue
            error_result = _format_error_result(e, "Scraping failed")
            error_result.update({"url": url, "retry_attempts": attempt, "duration": time.time() - start_time})
            return error_result

    return {
        "success": False,
        "url": url,
        "error": f"All {retry_count + 1} attempts failed",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": time.time() - start_time,
    }


async def take_screenshot(
    url: str,
    output_path: str = "",
    selector: Optional[str] = None,
    full_page: bool = False,
    wait_for_selector: Optional[str] = None,
    delay: int = 0,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    页面截图 - 支持整页截图和元素截图

    Args:
        url: 目标URL
        output_path: 截图保存路径
        selector: 指定元素截图(为空则截取整个视口)
        full_page: 是否截取整页
        wait_for_selector: 等待元素出现后再截图
        delay: 加载后延迟时间(毫秒)
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数
        viewport_width: 视口宽度
        viewport_height: 视口高度

    Returns:
        截图结果
    """
    start_time = time.time()
    logger.info(f"take_screenshot starting: {url}")
    if not output_path:
        output_path = _default_screenshot_path()
    output_path = _resolve_skill_path(output_path, kwargs.get("_project_path", ""))

    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {"success": False, "url": url, "screenshot_path": output_path, "error": f"URL validation failed: {url_error}", "platform": _get_platform().value}

    if selector:
        sv, se = _validate_selector(selector)
        if not sv:
            return {"success": False, "url": url, "screenshot_path": output_path, "error": f"Selector invalid: {se}", "platform": _get_platform().value}

    if wait_for_selector:
        sv, se = _validate_selector(wait_for_selector)
        if not sv:
            return {"success": False, "url": url, "screenshot_path": output_path, "error": f"Wait selector invalid: {se}", "platform": _get_platform().value}

    if delay < 0 or delay > 30000:
        return {"success": False, "url": url, "screenshot_path": output_path, "error": "delay must be between 0-30000ms", "platform": _get_platform().value}

    if viewport_width < 100 or viewport_width > 5000 or viewport_height < 100 or viewport_height > 5000:
        return {"success": False, "url": url, "screenshot_path": output_path, "error": "Viewport dimensions must be between 100-5000 pixels", "platform": _get_platform().value}

    for attempt in range(retry_count + 1):
        try:
            async with _browser_context(headless, browser_type, timeout) as (browser, context, page):
                result = {
                    "success": True,
                    "url": url,
                    "screenshot_path": output_path,
                    "selector": selector,
                    "full_page": full_page,
                    "viewport": {"width": viewport_width, "height": viewport_height},
                    "platform": _get_platform().value,
                    "duration": 0,
                    "error": None,
                    "retry_attempts": 0,
                }

                await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"Navigated to: {url}")

                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)

                if delay > 0:
                    await page.wait_for_timeout(delay)

                await page.wait_for_load_state("load")

                os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

                if selector:
                    element = await page.query_selector(selector)
                    if element:
                        await element.screenshot(path=output_path)
                        result["element_found"] = True
                        element_info = await page.evaluate("""(el) => {
                            const rect = el.getBoundingClientRect();
                            return {
                                tag: el.tagName.toLowerCase(),
                                visible: el.offsetParent !== null,
                                position: {
                                    x: Math.round(rect.x), y: Math.round(rect.y),
                                    width: Math.round(rect.width), height: Math.round(rect.height)
                                }
                            };
                        }""", element)
                        result["element_info"] = element_info
                    else:
                        result["success"] = False
                        result["error"] = f"Element not found: {selector}"
                        result["element_found"] = False
                else:
                    await page.screenshot(path=output_path, full_page=full_page)

                result["file_exists"] = os.path.exists(output_path)
                if result["file_exists"]:
                    result["file_size"] = os.path.getsize(output_path)
                else:
                    result["success"] = False
                    result["error"] = "Screenshot file not generated"

                result["retry_attempts"] = attempt
                result["duration"] = time.time() - start_time
                return result

        except ImportError:
            return {"success": False, "url": url, "screenshot_path": output_path, "error": "Playwright not installed", "error_type": "import_error", "platform": _get_platform().value}
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                await asyncio.sleep(1)
                continue
            error_result = _format_error_result(e, "Screenshot failed")
            error_result.update({"url": url, "screenshot_path": output_path, "retry_attempts": attempt, "duration": time.time() - start_time})
            return error_result

    return {
        "success": False,
        "url": url,
        "screenshot_path": output_path,
        "error": f"All {retry_count + 1} attempts failed",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": time.time() - start_time,
    }


async def test_element_exists(
    url: str,
    selector: str,
    wait_for_selector: Optional[str] = None,
    timeout: int = 30000,
    headless: bool = True,
    browser_type: str = "chromium",
    retry_count: int = 2,
    check_visibility: bool = True,
    **kwargs: Any,
) -> Dict[str, Any]:
    """
    测试页面元素是否存在 - 适用于前端测试

    Args:
        url: 目标URL
        selector: CSS选择器
        wait_for_selector: 等待元素出现
        timeout: 超时时间(毫秒)
        headless: 是否无头模式
        browser_type: 浏览器类型
        retry_count: 重试次数
        check_visibility: 是否检查元素可见性

    Returns:
        测试结果
    """
    start_time = time.time()
    logger.info(f"test_element_exists starting: {url}, selector: {selector}")

    url_valid, url_error = _validate_url(url)
    if not url_valid:
        return {"success": False, "url": url, "selector": selector, "exists": False, "error": f"URL validation failed: {url_error}", "platform": _get_platform().value}

    sv, se = _validate_selector(selector)
    if not sv:
        return {"success": False, "url": url, "selector": selector, "exists": False, "error": f"Selector invalid: {se}", "platform": _get_platform().value}

    if wait_for_selector:
        sv, se = _validate_selector(wait_for_selector)
        if not sv:
            return {"success": False, "url": url, "selector": selector, "exists": False, "error": f"Wait selector invalid: {se}", "platform": _get_platform().value}

    for attempt in range(retry_count + 1):
        try:
            async with _browser_context(headless, browser_type, timeout) as (browser, context, page):
                result = {
                    "success": True,
                    "url": url,
                    "selector": selector,
                    "exists": False,
                    "visible": False,
                    "count": 0,
                    "platform": _get_platform().value,
                    "duration": 0,
                    "error": None,
                    "retry_attempts": 0,
                }

                await page.goto(url, wait_until="domcontentloaded")
                logger.info(f"Navigated to: {url}")

                if wait_for_selector:
                    await page.wait_for_selector(wait_for_selector, timeout=timeout)

                await page.wait_for_load_state("load")

                elements = await page.query_selector_all(selector)
                result["count"] = len(elements)
                result["exists"] = len(elements) > 0

                if elements:
                    first_element = elements[0]
                    element_info = await page.evaluate("""(el, checkVisibility) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        const attributes = {};
                        for (const attr of el.attributes) {
                            attributes[attr.name] = attr.value;
                        }
                        return {
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText.trim().substring(0, 200),
                            visible: checkVisibility ? (el.offsetParent !== null &&
                                     style.display !== 'none' &&
                                     style.visibility !== 'hidden' &&
                                     rect.width > 0 && rect.height > 0) : true,
                            position: { x: Math.round(rect.x), y: Math.round(rect.y),
                                        width: Math.round(rect.width), height: Math.round(rect.height) },
                            style: { display: style.display, visibility: style.visibility, opacity: style.opacity },
                            attributes: attributes,
                            classes: el.className.split(' ').filter(c => c.trim()),
                            id: el.id || ''
                        };
                    }""", first_element, check_visibility)

                    result["element_info"] = element_info
                    result["visible"] = element_info["visible"]

                    if len(elements) > 1:
                        result["all_elements"] = []
                        for i, element in enumerate(elements[:10]):
                            basic_info = await page.evaluate("""(el) => {
                                const rect = el.getBoundingClientRect();
                                return { tag: el.tagName.toLowerCase(), text: el.innerText.trim().substring(0, 50),
                                         position: { x: Math.round(rect.x), y: Math.round(rect.y) } };
                            }""", element)
                            result["all_elements"].append(basic_info)

                result["retry_attempts"] = attempt
                result["duration"] = time.time() - start_time
                return result

        except ImportError:
            return {"success": False, "url": url, "selector": selector, "exists": False, "error": "Playwright not installed", "error_type": "import_error", "platform": _get_platform().value}
        except Exception as e:
            if attempt < retry_count:
                logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                await asyncio.sleep(1)
                continue
            error_result = _format_error_result(e, "Element test failed")
            error_result.update({"url": url, "selector": selector, "exists": False, "retry_attempts": attempt, "duration": time.time() - start_time})
            return error_result

    return {
        "success": False,
        "url": url,
        "selector": selector,
        "exists": False,
        "error": f"All {retry_count + 1} attempts failed",
        "error_type": "max_retries_exceeded",
        "platform": _get_platform().value,
        "retry_attempts": retry_count,
        "duration": time.time() - start_time,
    }


async def _get_system_browser_info() -> Dict[str, Any]:
    """
    Get 系统浏览器信息 -  with 于诊断和调试
    
    Returns:
        浏览器信息
    """
    platform_type = _get_platform()
    browsers = _detect_installed_browsers()
    
    return {
        "platform": platform_type.value,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "python_version": sys.version,
        "detected_browsers": [
            {
                "type": b.type.value,
                "executable_path": b.executable_path,
                "version": b.version,
                "installed": b.installed,
                "is_playwright_managed": b.is_playwright_managed
            }
            for b in browsers
        ],
        "default_paths": {
            browser_type.value: paths
            for browser_type, paths in _get_default_browser_paths().items()
            if paths
        },
        "timestamp": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
    }


async def _check_playwright_installation() -> Dict[str, Any]:
    """
    检查Playwright安装状态
    
    Returns:
        安装状态信息
    """
    result = {
        "playwright_installed": False,
        "browsers_installed": [],
        "platform": _get_platform().value,
        "errors": []
    }
    
    # 检查Playwright包
    try:
        from playwright._repo_version import version as playwright_version
        result["playwright_installed"] = True
        result["playwright_version"] = playwright_version
    except ImportError:
        # 尝试其他方式
        try:
            import playwright
            result["playwright_installed"] = True
            result["playwright_version"] = "Unknown (installed)"
        except ImportError:
            result["errors"].append("Playwright package not installed")
            return result
    
    # 检查浏览器
    try:
        from playwright._impl._driver import compute_driver_executable
        driver_path = compute_driver_executable()
        if driver_path:
            result["driver_path"] = str(driver_path)
            
            # 检查Playwright管理的浏览器
            playwright_dir = os.path.dirname(os.path.dirname(str(driver_path)))
            browsers_dir = os.path.join(playwright_dir, ".local-browsers")
            
            if os.path.exists(browsers_dir):
                for browser_type in BrowserType:
                    browser_path = os.path.join(browsers_dir, browser_type.value)
                    if os.path.exists(browser_path):
                        result["browsers_installed"].append(browser_type.value)
    except Exception as e:
        result["errors"].append(f"Error checking browser: {str(e)}")
    
    # 检查系统浏览器
    system_browsers = _detect_installed_browsers()
    result["system_browsers"] = [
        {
            "type": b.type.value,
            "version": b.version,
            "is_playwright_managed": b.is_playwright_managed
        }
        for b in system_browsers
    ]
    
    return result


# 使 with 示例
async def _example_usage():
    """使 with 示例"""
    print("=== Playwright Skill Usage Examples ===")

    print("\n1. System browser info:")
    browser_info_result = asyncio.run(_get_system_browser_info())
    print(f"Platform: {browser_info_result['platform']}")
    print(f"Detected browsers: {len(browser_info_result['detected_browsers'])}")

    print("\n2. Playwright installation status:")
    install_status = asyncio.run(_check_playwright_installation())
    print(f"Playwright installed: {install_status['playwright_installed']}")
    if install_status['playwright_installed']:
        print(f"Version: {install_status.get('playwright_version', 'Unknown')}")
        print(f"Playwright-managed browsers: {', '.join(install_status['browsers_installed'])}")
    else:
        for error in install_status.get('errors', []):
            print(f"  - {error}")

    print("\n3. Test simple operation:")
    test_url = "https://www.google.com"
    try:
        print(f"Test URL: {test_url}")
        test_result = asyncio.run(test_element_exists(
            url=test_url,
            selector="input[name='q']",
            timeout=15000
        ))
        if test_result['success']:
            print(f"Element exists: {test_result['exists']}")
            if test_result['exists']:
                print(f"Element count: {test_result['count']}")
                print(f"Element visible: {test_result['visible']}")
        else:
            print(f"Test failed: {test_result['error']}")
    except Exception as e:
        print(f"Example execution error: {str(e)}")

    print("\n=== End of examples ===")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(_example_usage())
