"""浏览器。默认用 undetected-chromedriver，打不开就退回普通 Chrome。"""
import logging
import os
import random
import shutil
import subprocess
import tempfile
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import config

logger = logging.getLogger("crawl.browser")
PAGE_LOAD_TIMEOUT = 45

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
UA_POOL = (
    DEFAULT_UA,
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)
WINDOW_POOL = ("1920,1080", "1680,1050", "1536,864")


class BrowserError(RuntimeError):
    pass


@dataclass
class BrowserProfile:
    headless: bool
    engine: str
    user_agent: str
    window: str
    lang: str
    timezone: str
    fingerprint: str

    @classmethod
    def resolve(cls, node=None):
        node = node or {}
        headless = config.CRAWL_HEADLESS if node.get("headless") is None else bool(node.get("headless"))
        engine = (node.get("browser") or config.CRAWL_BROWSER or "undetected").strip()
        fingerprint = (node.get("fingerprint") or config.CRAWL_FINGERPRINT or "fixed").strip()
        window = node.get("window") or config.CRAWL_WINDOW or "1920,1080"
        user_agent = node.get("user_agent") or config.CRAWL_USER_AGENT or ""
        if fingerprint == "rotate":
            user_agent = user_agent or random.choice(UA_POOL)
            if not node.get("window"):
                window = random.choice(WINDOW_POOL)
        if not user_agent:
            user_agent = DEFAULT_UA
        return cls(
            headless=headless,
            engine=engine,
            user_agent=user_agent,
            window=window,
            lang=node.get("lang") or config.CRAWL_LANG,
            timezone=node.get("timezone") or config.CRAWL_TIMEZONE,
            fingerprint=fingerprint,
        )

    def describe(self):
        mode = "无头" if self.headless else "有界面"
        return f"{self.engine}，{mode}，指纹 {self.fingerprint}，窗口 {self.window}"


def _apply_args(options, profile):
    width, height = (profile.window.split(",") + ["1080"])[:2]
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument(f"--lang={profile.lang.split(',')[0]}")
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument(f"--user-agent={profile.user_agent}")
    if profile.headless:
        options.add_argument("--headless=new")
    profile_dir = tempfile.mkdtemp(prefix="six-chrome-")
    options.add_argument(f"--user-data-dir={profile_dir}")
    return profile_dir


def _chrome_binary():
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    try:
        import undetected_chromedriver as uc
        found = uc.find_chrome_executable()
        if found and os.path.isfile(found):
            return found
    except Exception:
        pass
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


def _version_text(executable):
    if os.name == "nt":
        try:
            import win32api
            info = win32api.GetFileVersionInfo(str(executable), "\\")
            high, low = info["FileVersionMS"], info["FileVersionLS"]
            return f"{high >> 16}.{high & 65535}.{low >> 16}.{low & 65535}"
        except Exception:
            pass
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    output = subprocess.check_output(
        [str(executable), "--version"], timeout=8, creationflags=flags, stderr=subprocess.STDOUT,
    )
    text = output.decode(errors="replace")
    import re
    match = re.search(r"\b\d+\.\d+\.\d+\.\d+\b", text)
    if not match:
        raise BrowserError(f"读不到浏览器版本：{executable}")
    return match.group()


def _matching_driver(version):
    with _driver_lock():
        return _matching_driver_locked(version)


def _matching_driver_locked(version):
    major = version.split(".")[0]
    roots = [Path.home() / ".wdm", Path.cwd() / ".wdm"]
    name = "chromedriver.exe" if os.name == "nt" else "chromedriver"
    candidates = []
    for root in roots:
        if root.exists():
            candidates.extend(sorted(root.rglob(name), key=lambda item: item.stat().st_mtime, reverse=True))
    for candidate in candidates:
        try:
            if _version_text(candidate).split(".")[0] == major:
                return candidate
        except Exception:
            continue
    from webdriver_manager.chrome import ChromeDriverManager
    return Path(ChromeDriverManager(driver_version=version).install())


def _driver_lock():
    """下载和缓存驱动时跨进程互斥，避免两个爬虫同时写同一个 chromedriver。"""
    from contextlib import contextmanager
    lock_path = Path(__file__).resolve().parents[1] / "runtime" / "locks" / "chromedriver.lock"

    @contextmanager
    def _locked():
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(lock_path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()

    return _locked()


def _paint(driver, profile):
    try:
        driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": profile.timezone})
    except Exception:
        logger.info("时区指纹未写上，继续采集")
    try:
        driver.execute_cdp_cmd("Network.setUserAgentOverride", {
            "userAgent": profile.user_agent,
            "acceptLanguage": profile.lang,
            "platform": "Win32",
        })
    except Exception:
        logger.info("语言指纹未写上，继续采集")


def _open_undetected(profile):
    import undetected_chromedriver as uc
    binary = _chrome_binary()
    if not binary:
        raise BrowserError("没找到本机 Chrome")
    version = _version_text(binary)
    source = _matching_driver(version)
    session = Path(tempfile.mkdtemp(prefix="six-driver-"))
    driver_path = session / f"chromedriver-{uuid.uuid4().hex}{source.suffix}"
    shutil.copy2(source, driver_path)
    options = uc.ChromeOptions()
    profile_dir = _apply_args(options, profile)
    driver = uc.Chrome(
        options=options,
        headless=profile.headless,
        version_main=int(version.split(".")[0]),
        driver_executable_path=str(driver_path),
        browser_executable_path=binary,
        use_subprocess=True,
    )
    return driver, profile_dir


def _open_selenium(profile):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    options = Options()
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    profile_dir = _apply_args(options, profile)
    binary = _chrome_binary()
    if binary:
        options.binary_location = binary
    system_driver = shutil.which("chromedriver")
    if system_driver:
        service = Service(executable_path=system_driver)
    else:
        from webdriver_manager.chrome import ChromeDriverManager
        service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options), profile_dir


def _pids(driver):
    pids = []
    service = getattr(driver, "service", None)
    process = getattr(service, "process", None)
    if process is not None and getattr(process, "pid", None):
        pids.append(int(process.pid))
    browser_pid = getattr(driver, "browser_pid", None)
    if browser_pid:
        pids.append(int(browser_pid))
    return pids


def open_browser(profile):
    engine = (profile.engine or "undetected").lower()
    if engine == "selenium":
        driver, profile_dir = _open_selenium(profile)
    else:
        try:
            driver, profile_dir = _open_undetected(profile)
        except Exception as exc:
            logger.warning("反检测浏览器没起来，改用普通 Chrome：%s", exc)
            driver, profile_dir = _open_selenium(profile)
    _paint(driver, profile)
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver, profile_dir


@contextmanager
def browser_session(profile, source_id=""):
    from collect.infrastructure.process_guard import hold_job, remember, release
    driver, profile_dir = open_browser(profile)
    key = source_id or "browser"
    pids = _pids(driver)
    remember(key, os.path.basename(profile_dir), pids)
    hold_job(key, pids)
    try:
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            logger.info("浏览器关闭时有残留，改为按进程清理")
        # 反检测驱动析构时还会再关一次，Windows 上句柄已经无效。
        driver.quit = lambda: None
        release(key)
