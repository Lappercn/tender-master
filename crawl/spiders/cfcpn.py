"""金采网（中国金融集中采购网）。4个采购与结果栏目翻页采集。"""
import logging
from urllib.parse import urljoin

from selenium.webdriver.common.by import By

from collect.sources.cfcpn_fin.constants import DETAIL_BOX, LIST_ROW, ORIGIN, list_url
from collect.sources.cfcpn_fin.source import SOURCE
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


class CfcpnSpider:
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
            if "supplierLogin" in (driver.current_url or ""):
                mark(store, self.spec, channel_id, label, page_no, result, "需要配置合法供应商登录会话")
                return "需要供应商登录会话"
            try:
                page.wait_css("#noticeUl")
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
                try:
                    title_tag = items[idx].find_element(By.CSS_SELECTOR, "a.cfcpn-notice-title")
                    date_tag = items[idx].find_element(By.CSS_SELECTOR, "h6.cfcpn-list-date")
                    title = " ".join(((title_tag.get_attribute("title") or title_tag.text) or "").split())
                    date_text = (date_tag.text or "").strip()[:10]
                except Exception:
                    continue
                decision = judge_date(date_text, start, end)
                if decision == "stop":
                    stop = True
                    break
                if decision != "take":
                    continue
                self._take_row(driver, page, job, store, channel_id, label, title_tag, title, date_text, result, start, end)
            if stop:
                mark(store, self.spec, channel_id, label, page_no, result, "日期已早于采集范围")
                return "日期已早于采集范围"
            if not self._next_page(driver, page):
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"

    def _next_page(self, driver, page):
        try:
            next_li = driver.find_element(By.ID, "img_next")
            if "disabled" in (next_li.get_attribute("class") or ""):
                return False
            btn = next_li.find_element(By.TAG_NAME, "a")
            driver.execute_script("arguments[0].click();", btn)
            page.pause(1.5, 3.0)
            return True
        except Exception:
            return page.click_next()

    def _take_row(self, driver, page, job, store, channel_id, label, title_tag, title, date_text, result, start, end):
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, date_text)
        if skip_as_duplicate(existing, fingerprint) and self._files_ready(store, existing, fingerprint, label, title, result):
            return
        main = driver.current_window_handle
        try:
            driver.execute_script("arguments[0].click();", title_tag)
            page.pause(1.5, 3.0)
            for h in driver.window_handles:
                if h != main:
                    driver.switch_to.window(h)
                    break
            page.wait_css(DETAIL_BOX)
            page.glance()
            content = driver.find_element(By.CSS_SELECTOR, DETAIL_BOX)
            html = content.get_attribute("outerHTML") or ""
            text = html_to_text(html) or (content.text or "")
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
            purchaser, method, area = "", "", ""
            for info in driver.find_elements(By.CSS_SELECTOR, "div.cfcpn-announcements-info-main"):
                txt = (info.text or "").strip()
                if "采购人" in txt:
                    purchaser = txt.replace("采购人", "").strip()
                elif "采购方式" in txt:
                    method = txt.replace("采购方式", "").strip()
                elif "所在地区" in txt:
                    area = txt.replace("所在地区", "").strip()
            urls = []
            for anchor in driver.find_elements(By.CSS_SELECTOR, "#file-new a"):
                href = (anchor.get_attribute("href") or "").strip()
                if href and not href.startswith("javascript:") and href not in urls:
                    urls.append(urljoin(ORIGIN, href))
            doc = build_notice(
                crawler_id=self.spec.id,
                source=self.spec.source,
                title=title,
                url=driver.current_url,
                content_id=fingerprint,
                create_time=date_text,
                channel_id=channel_id,
                channel_label=label,
                node_id=job.node_id,
                detail_text=text,
                detail_html=html,
                file_urls=urls,
                purchaser_hint=purchaser,
                purchase_method_hint=method,
                area_hint=area,
                biz_net=self.spec.net_name,
                industry_hint="金融采购",
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
