"""中国烟草电子采购平台。5个公开招标与结果栏目翻页采集。"""
import logging
from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from collect.sources.tobacco_cgjy.constants import DETAIL_BOX, FILE_HINTS, LIST_ROW, ORIGIN, list_url
from collect.sources.tobacco_cgjy.source import SOURCE
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


class TobaccoSpider:
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
                page.wait_css("ul.searchList")
            except Exception:
                mark(store, self.spec, channel_id, label, page_no, result, "页面上没有列表")
                return "页面上没有列表"
            rows = self._read_rows(driver)
            if not rows:
                mark(store, self.spec, channel_id, label, page_no, result, "这一页没有公告")
                return "这一页没有公告"
            mark(store, self.spec, channel_id, label, page_no, result, f"正在看第 {page_no} 页")
            for row in rows:
                decision = judge_date(row["date"], start, end)
                if decision == "stop":
                    mark(store, self.spec, channel_id, label, page_no, result, "日期已早于采集范围")
                    return "日期已早于采集范围"
                if decision != "take":
                    continue
                self._take_row(driver, page, job, store, channel_id, label, row, result, start, end)
            if not page.click_next():
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"

    def _read_rows(self, driver):
        rows = []
        for item in driver.find_elements(By.CSS_SELECTOR, LIST_ROW):
            try:
                date_raw = (item.find_element(By.CLASS_NAME, "release_date").text or "").replace("发布日期:", "").strip()
                date_text = date_raw.replace(".", "-")[:10]
                span = item.find_element(By.CLASS_NAME, "span_hover")
                title = (span.get_attribute("title") or span.text or "").strip()
                link = item.find_element(By.TAG_NAME, "a")
                href = (link.get_attribute("href") or "").strip()
                tag = ""
                try:
                    tag = (item.find_element(By.TAG_NAME, "em").text or "").strip()
                except Exception:
                    pass
                if title and href:
                    rows.append({
                        "title": " ".join(title.split()),
                        "url": urljoin(ORIGIN, href),
                        "date": date_text,
                        "tag": tag,
                    })
            except Exception:
                continue
        return rows

    def _take_row(self, driver, page, job, store, channel_id, label, row, result, start, end):
        title = row["title"]
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, row["date"])
        if skip_as_duplicate(existing, fingerprint) and self._files_ready(store, existing, fingerprint, label, title, result):
            return
        main = driver.current_window_handle
        try:
            page.open_tab(row["url"])
            page.pause(1.0, 2.0)
            page.wait_css(DETAIL_BOX)
            page.glance()
            content = driver.find_element(By.CSS_SELECTOR, DETAIL_BOX)
            html = content.get_attribute("outerHTML") or ""
            text = html_to_text(html) or (content.text or "")
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
            urls = []
            seen = set()
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
                purchase_method_hint=row["tag"],
                biz_net=self.spec.net_name,
                industry_hint="烟草行业",
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
            page.close_tab(main)
            page.human_gap("detail")

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
