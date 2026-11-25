"""翻页和打开详情时共用的等待、滚动。间隔随机，连续多了会自己停一下。"""
import logging
import random
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


PACES = {
    "calm": {"page": (4.0, 9.0), "detail": (3.0, 7.0), "rest": (15.0, 40.0), "every": (6, 10)},
    "normal": {"page": (2.0, 5.0), "detail": (1.8, 4.5), "rest": (8.0, 22.0), "every": (8, 14)},
}


def pace_choices():
    labels = {"calm": "从容", "normal": "正常"}
    hints = {
        "calm": "间隔更长，连续多了会多停一会儿",
        "normal": "间隔随机，连续打开多条后会停一下",
    }
    opening = [
        "打开一条公告时，点标题后停 1.5～3 秒，新窗口出来再停 1.5～3 秒，再向下扫 2～4 屏，每屏停 0.4～1.2 秒。这几下不计入上面的连续次数。",
        "单次停留满 8 秒，采集日志会记一行「停 N 秒，避开固定频率」。",
        "正在采集时改节奏不会立刻生效。先关闭，再启动，才按新的节奏走。",
    ]
    items = []
    for code in ("calm", "normal"):
        spec = PACES[code]
        items.append({
            "code": code,
            "label": labels[code],
            "hint": hints[code],
            "steps": [
                f"翻页、进入栏目：每次随机停 {_span_text(spec['page'], '秒')}。",
                f"看完一条公告，再看下一条：随机停 {_span_text(spec['detail'], '秒')}。",
                f"连续做了 {_span_text(spec['every'], '次')} 之后，额外再停 {_span_text(spec['rest'], '秒')}。连续次数和这次长停都是随机的，避免固定频率被网站拦住。",
                *opening,
            ],
        })
    return items


def _span_text(pair, unit):
    return f"{_num(pair[0])}～{_num(pair[1])} {unit}"


def _num(value):
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def gap_plan(pace, kind, done, rest_every, rand=None):
    """算出这一次要停多久。连续多了就额外多停，避免固定频率被拦。"""
    rand = rand or random
    spec = PACES.get(pace) or PACES["normal"]
    low, high = spec.get(kind) or spec["detail"]
    wait = rand.uniform(low, high)
    done += 1
    if rest_every <= 0:
        rest_every = rand.randint(*spec["every"])
    if done >= rest_every:
        wait += rand.uniform(*spec["rest"])
        wait += min(30, done // 12) * rand.uniform(0.3, 0.9)
        done = 0
        rest_every = rand.randint(*spec["every"])
    return wait, done, rest_every


class Page:
    def __init__(self, driver, pace="normal"):
        self.driver = driver
        self.pace = pace if pace in PACES else "normal"
        self.wait = WebDriverWait(driver, 25)
        self._done = 0
        self._rest_every = 0

    def pause(self, low=1.5, high=3.0):
        time.sleep(random.uniform(low, high))

    def human_gap(self, kind="detail"):
        seconds, self._done, self._rest_every = gap_plan(self.pace, kind, self._done, self._rest_every)
        if seconds >= 8:
            logging.getLogger("crawl.runtime").info("停 %.0f 秒，避开固定频率", seconds)
        time.sleep(seconds)

    def glance(self):
        try:
            height = self.driver.execute_script("return document.body.scrollHeight") or 0
            view = self.driver.execute_script("return window.innerHeight") or 800
            top = 0
            for _ in range(random.randint(2, 4)):
                if top + view >= height:
                    break
                top += random.randint(200, 500)
                self.driver.execute_script("window.scrollTo(0, arguments[0]);", top)
                time.sleep(random.uniform(0.4, 1.2))
        except Exception:
            return

    def wait_css(self, css):
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))

    def click_css(self, css):
        element = self.wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css)))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        self.pause(0.4, 1.0)
        try:
            element.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", element)
        return element

    def open_tab(self, url):
        self.driver.execute_script("window.open('about:blank','_blank');")
        self.driver.switch_to.window(self.driver.window_handles[-1])
        self.driver.get(url)

    def close_tab(self, main_handle):
        if self.driver.current_window_handle != main_handle and len(self.driver.window_handles) > 1:
            self.driver.close()
        self.driver.switch_to.window(main_handle)

    def click_next(self):
        script = """
            const words = ['>', '›', '下一页', '下页'];
            const nodes = Array.from(document.querySelectorAll('button, a, li'));
            const next = nodes.find(node => {
                const text = (node.innerText || '').trim();
                const blocked = node.disabled || /disabled|inactive/.test(node.className || '');
                return words.includes(text) && !blocked;
            });
            if (!next) return false;
            next.click();
            return true;
        """
        return bool(self.driver.execute_script(script))
