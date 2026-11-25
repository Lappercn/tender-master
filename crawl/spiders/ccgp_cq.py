"""重庆市政府采购网。公开采购公告栏目翻页采集。"""
import datetime
import logging
import re
from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from collect.sources.ccgp_chongqing.constants import DETAIL_BOX, FILE_HINTS, LIST_ROW, ORIGIN, list_url
from collect.sources.ccgp_chongqing.source import SOURCE
from crawl.browser import browser_session
from crawl.files import files_settled, store_files
from crawl.identity import content_id, skip_as_duplicate
from crawl.job import JobResult, channels_for
from crawl.progress import mark
from crawl.record import build_notice
from crawl.runtime import Page
from crawl.text import html_to_text
from crawl.trace import file_note, notice_line
from crawl.window import judge_date, label_of, outside_detail, window_bounds

logger = logging.getLogger(SOURCE.script)


def normalize_cq_date(raw_text, today=None):
    today = today or datetime.date.today()
    text = (raw_text or "").strip()
    if any(word in text for word in ("刚刚", "分钟前", "小时前", "秒前")):
        return today.isoformat()
    if "昨天" in text:
        return (today - datetime.timedelta(days=1)).isoformat()
    if "前天" in text:
        return (today - datetime.timedelta(days=2)).isoformat()
    match_days = re.search(r"(\d+)\s*天前", text)
    if match_days:
        return (today - datetime.timedelta(days=int(match_days.group(1)))).isoformat()
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text[:10]


class CcgpChongqingSpider:
    spec = SOURCE

    def run(self, job, store, profile):
        result = JobResult()
        with browser_session(profile, self.spec.id) as driver:
            page = Page(driver, job.pace)
            logger.info("打开 %s %s，范围 %s", self.spec.name, profile.describe(), label_of(job.span))
            for channel in channels_for(self.spec, job):
                channel_id, label = channel.code, channel.name
                try:
                    note = self._crawl_channel(driver, page, job, store, channel_id, label, result)
                    result.channels.append(f"{label}:{note}")
                except Exception as exc:
                    result.failed += 1
                    result.error = str(exc)
                    result.channels.append(f"{label}:失败")
                    logger.exception("栏目失败 %s", label)
        result.note = "；".join(result.channels)
        if result.saved == 0 and result.error and result.failed:
            result.status = "failed"
        elif result.failed:
            result.status = "partial"
        return result

    def _crawl_channel(self, driver, page, job, store, channel_id, label, result):
        logger.info("栏目 %s", label)
        start, end = window_bounds(job.lookback_hours)
        driver.get(list_url(channel_id))
        page_no = 0
        while True:
            page_no += 1
            if page_no > job.max_pages:
                mark(store, self.spec, channel_id, label, page_no, result, "到达单次页数上限")
                return "到达单次页数上限"
            if job.page_end and page_no > job.page_end:
                mark(store, self.spec, channel_id, label, page_no, result, "到达指定页")
                return "到达指定页"
            page.human_gap("page")
            try:
                page.wait_css(".notice-list")
            except Exception:
                mark(store, self.spec, channel_id, label, page_no, result, "页面上没有列表")
                return "页面上没有列表"
            items = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
            if not items:
                mark(store, self.spec, channel_id, label, page_no, result, "这一页没有公告")
                return "这一页没有公告"
            mark(store, self.spec, channel_id, label, page_no, result, f"正在看第 {page_no} 页")
            stop = False
            for idx in range(len(items)):
                items = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
                if idx >= len(items):
                    break
                row = self._parse_item(items[idx])
                if not row:
                    continue
                decision = judge_date(row["date"], start, end)
                if decision == "stop":
                    stop = True
                    break
                if decision != "take":
                    continue
                self._take_row(driver, page, job, store, channel_id, label, items[idx], row, result, start, end)
            if stop:
                mark(store, self.spec, channel_id, label, page_no, result, "日期已早于采集范围")
                return "日期已早于采集范围"
            if not page.click_next():
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"

    def _parse_item(self, item):
        try:
            title_elem = item.find_element(By.CSS_SELECTOR, ".list-group-item-heading")
            title = " ".join((title_elem.text or "").split())
            raw_date = (item.find_element(By.CSS_SELECTOR, ".display-date").text or "").strip()
            date_text = normalize_cq_date(raw_date)
        except Exception:
            return None
        area = "重庆"
        try:
            area = (item.find_element(By.CSS_SELECTOR, ".tag-area").text or "").strip() or "重庆"
        except Exception:
            pass
        method = ""
        try:
            method = (item.find_element(By.CSS_SELECTOR, ".tag-purchase").text or "").strip()
        except Exception:
            pass
        buyer = ""
        try:
            buyer = re.sub(r"采购人[：:]\s*", "", item.find_element(By.CSS_SELECTOR, ".buyer").text or "").strip()
        except Exception:
            pass
        agent = ""
        try:
            agent = re.sub(r"代理机构[：:]\s*", "", item.find_element(By.CSS_SELECTOR, ".agency").text or "").strip()
        except Exception:
            pass
        return {
            "title": title,
            "date": date_text,
            "area": area,
            "method": method,
            "buyer": buyer,
            "agent": agent,
        }

    def _take_row(self, driver, page, job, store, channel_id, label, item_elem, row, result, start, end):
        title = row["title"]
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, row["date"])
        if skip_as_duplicate(existing, fingerprint) and self._files_ready(store, existing, fingerprint, label, title, result):
            return
        main = driver.current_window_handle
        before_handles = set(driver.window_handles)
        try:
            title_elem = item_elem.find_element(By.CSS_SELECTOR, ".list-group-item-heading")
            driver.execute_script("arguments[0].click();", title_elem)
            page.pause(1.0, 2.0)
            after_handles = driver.window_handles
            if len(after_handles) > len(before_handles):
                for h in after_handles:
                    if h not in before_handles:
                        driver.switch_to.window(h)
                        break
            page.wait_css(DETAIL_BOX)
            page.glance()
            content = self._detail_content(driver)
            html = content.get_attribute("outerHTML") or "" if content else ""
            text = html_to_text(html) or (content.text if content else "")
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
            urls = []
            seen = set()
            if content:
                for anchor in content.find_elements(By.TAG_NAME, "a"):
                    href = (anchor.get_attribute("href") or "").strip()
                    if not href or href.startswith("javascript:") or href in seen:
                        continue
                    if any(hint in href.lower() for hint in FILE_HINTS):
                        seen.add(href)
                        urls.append(urljoin(ORIGIN, href))
            doc = build_notice(
                crawler_id=self.spec.id,
                source=self.spec.source,
                title=title,
                url=driver.current_url,
                content_id=fingerprint,
                create_time=row["date"],
                channel_id=channel_id,
                channel_label=label,
                node_id=job.node_id,
                detail_text=text,
                detail_html=html,
                file_urls=urls,
                purchaser_hint=row["buyer"],
                agent_hint=row["agent"],
                area_hint=row["area"],
                purchase_method_hint=row["method"],
                biz_net=self.spec.net_name,
                industry_hint="综合政务",
            )
            saved = store_files(self.spec.net, self.spec.id, fingerprint, urls)
            doc["files"] = saved
            doc["script"] = self.spec.script
            outcome = store.save_notice(self.spec.id, doc)
            if outcome == "duplicate":
                store.attach_files(self.spec.id, fingerprint, saved, urls)
                result.skipped += 1
                step = "补附件"
            else:
                result.saved += 1
                step = "已保存"
            logger.info("%s", notice_line(label, step, title, file_note(saved)))
        except Exception as exc:
            result.failed += 1
            logger.warning("%s", notice_line(label, "失败", title, str(exc)[:120]))
        finally:
            if len(driver.window_handles) > 1:
                page.close_tab(main)
            else:
                driver.back()
            page.human_gap("detail")

    def _detail_content(self, driver):
        for css in ("div.wrap-post", "div.notice-detail", "div.notice-content", "body"):
            found = driver.find_elements(By.CSS_SELECTOR, css)
            if found and (found[0].text or "").strip():
                return found[0]
        return None

    def _files_ready(self, store, existing, fingerprint, label, title, result):
        if files_settled(existing):
            result.skipped += 1
            logger.info("%s", notice_line(label, "跳过", title, "附件已齐"))
            return True
        urls = [url for url in (existing or {}).get("fileUrl") or [] if url]
        if not urls:
            return False
        saved = store_files(self.spec.net, self.spec.id, fingerprint, urls, existing=(existing or {}).get("files"))
        store.attach_files(self.spec.id, fingerprint, saved, urls)
        result.skipped += 1
        logger.info("%s", notice_line(label, "补附件", title, file_note(saved)))
        return True
