"""中国电信阳光采购网。10个公开采购栏目翻页采集。"""
import logging

from selenium.webdriver.common.by import By

from collect.sources.chinatelecom_sun.constants import DETAIL_BOX, HOME_URL, LIST_ROW
from collect.sources.chinatelecom_sun.source import SOURCE
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


class ChinaTelecomSpider:
    spec = SOURCE

    def run(self, job, store, profile):
        result = JobResult()
        with browser_session(profile, self.spec.id) as driver:
            page = Page(driver, job.pace)
            logger.info("打开 %s %s，范围 %s", self.spec.name, profile.describe(), label_of(job.span))
            driver.get(HOME_URL)
            page.human_gap("page")
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
        if not self._select_nav(driver, page, label):
            mark(store, self.spec, channel_id, label, 1, result, "未找到分类导航")
            return "未找到分类导航"
        start, end = window_bounds(job.lookback_hours)
        page_no = 0
        while True:
            page_no += 1
            if page_no > job.max_pages:
                mark(store, self.spec, channel_id, label, page_no, result, "到达单次页数上限")
                return "到达单次页数上限"
            if job.page_end and page_no > job.page_end:
                mark(store, self.spec, channel_id, label, page_no, result, "到达指定页")
                return "到达指定页"
            try:
                page.wait_css(LIST_ROW)
            except Exception:
                mark(store, self.spec, channel_id, label, page_no, result, "页面上没有列表")
                return "页面上没有列表"
            rows = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
            if not rows:
                mark(store, self.spec, channel_id, label, page_no, result, "这一页没有公告")
                return "这一页没有公告"
            mark(store, self.spec, channel_id, label, page_no, result, f"正在看第 {page_no} 页")
            stop = False
            for index in range(len(rows)):
                rows = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
                if index >= len(rows):
                    break
                cols = rows[index].find_elements(By.TAG_NAME, "td")
                if len(cols) < 4:
                    continue
                date_text = (cols[-1].text or "").strip()[:10]
                decision = judge_date(date_text, start, end)
                if decision == "stop":
                    stop = True
                    break
                if decision != "take":
                    continue
                try:
                    title_elem = cols[0].find_element(By.CSS_SELECTOR, "div.noticeTitle")
                    title = " ".join((title_elem.text or "").split())
                except Exception:
                    continue
                self._take_row(driver, page, job, store, channel_id, label, title, date_text, title_elem, result, start, end)
            if stop:
                mark(store, self.spec, channel_id, label, page_no, result, "日期已早于采集范围")
                return "日期已早于采集范围"
            if not page.click_next():
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"
            page.human_gap("page")

    def _select_nav(self, driver, page, label):
        try:
            page.wait_css(".noticeNavbox")
        except Exception:
            return False
        for item in driver.find_elements(By.CSS_SELECTOR, "div.noticeNavItem"):
            if label in (item.text or ""):
                if "isActive" not in (item.get_attribute("class") or ""):
                    driver.execute_script("arguments[0].click();", item)
                    page.human_gap("page")
                return True
        return False

    def _take_row(self, driver, page, job, store, channel_id, label, title, date_text, title_elem, result, start, end):
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, date_text)
        if skip_as_duplicate(existing, fingerprint) and files_settled(existing):
            result.skipped += 1
            logger.info("%s", notice_line(label, "跳过", title, "附件已齐"))
            return
        main = driver.current_window_handle
        before_handles = set(driver.window_handles)
        try:
            driver.execute_script("arguments[0].click();", title_elem)
            page.pause(1.5, 3.0)
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
            annex_names = []
            for item in driver.find_elements(By.CSS_SELECTOR, "div.fileItem div.title div.el-tooltip"):
                name = " ".join((item.text or "").split())
                if name and name not in annex_names:
                    annex_names.append(name)
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
                file_urls=[],
                biz_net=self.spec.net_name,
                industry_hint="通信IT",
                extra={"annexNames": annex_names} if annex_names else {},
            )
            doc["files"] = store_files(self.spec.net, self.spec.id, fingerprint, [])
            doc["script"] = self.spec.script
            outcome = store.save_notice(self.spec.id, doc)
            if outcome == "duplicate":
                result.skipped += 1
                step = "跳过"
            else:
                result.saved += 1
                step = "已保存"
            logger.info("%s", notice_line(label, step, title, file_note(doc["files"])))
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
        for css in ("div.a-main", "div.main-content", "div.detail-box", "div.content", "body"):
            found = driver.find_elements(By.CSS_SELECTOR, css)
            if found and len((found[0].text or "").strip()) > 30:
                return found[0]
        return None
