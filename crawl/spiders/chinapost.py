"""中国邮政电子采购与供应平台。公开采购信息列表分页与PDF附件提取。"""
import logging
from urllib.parse import parse_qs, urljoin, urlparse

from selenium.webdriver.common.by import By

from collect.sources.chinapost_11185.constants import DETAIL_BOX, LIST_ROW, ORIGIN, list_url
from collect.sources.chinapost_11185.source import SOURCE
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


class ChinaPostSpider:
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
        page_no = max(1, job.page_start)
        seen = 0
        while True:
            seen += 1
            if seen > job.max_pages:
                mark(store, self.spec, channel_id, label, page_no, result, "到达单次页数上限")
                return "到达单次页数上限"
            if job.page_end and page_no > job.page_end:
                mark(store, self.spec, channel_id, label, page_no, result, "到达指定页")
                return "到达指定页"
            driver.get(list_url(channel_id, page_no))
            page.human_gap("page")
            try:
                page.wait_css(LIST_ROW)
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
            page_no += 1

    def _read_rows(self, driver):
        rows = []
        for item in driver.find_elements(By.CSS_SELECTOR, LIST_ROW):
            try:
                date_raw = (item.find_element(By.CSS_SELECTOR, "div.newsDate").text or "").strip()
                parts = date_raw.split()
                if len(parts) >= 2:
                    pub_date = f"{parts[0]}-{parts[1].replace('/', '-')}"
                else:
                    pub_date = date_raw.replace("\n", "-").replace("/", "-")
                link = item.find_element(By.TAG_NAME, "a")
                href = (link.get_attribute("href") or "").strip()
                title = (link.get_attribute("title") or "").strip()
                if not title:
                    title = (link.find_element(By.TAG_NAME, "h1").text or "").strip()
                project_code = ""
                method = ""
                deadline = ""
                for li in item.find_elements(By.CSS_SELECTOR, "ul.newsinfo li"):
                    txt = (li.text or "").strip()
                    if "项目编号" in txt:
                        project_code = txt.split("：")[-1].strip()
                    elif "采购方式" in txt:
                        method = txt.split("：")[-1].strip()
                    elif "截止时间" in txt:
                        deadline = txt.split("：")[-1].strip()
                if title and href:
                    rows.append({
                        "title": " ".join(title.split()),
                        "url": urljoin(ORIGIN, href),
                        "date": pub_date[:10],
                        "project_code": project_code,
                        "method": method,
                        "deadline": deadline,
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
            urls = []
            try:
                iframe = driver.find_element(By.ID, "pdfContainer")
                src = iframe.get_attribute("src") or ""
                if src:
                    qs = parse_qs(urlparse(src).query)
                    if "file" in qs and qs["file"]:
                        urls.append(urljoin(ORIGIN, qs["file"][0]))
            except Exception:
                pass
            html = ""
            text = ""
            for css in ("#main", "div.block", "body"):
                found = driver.find_elements(By.CSS_SELECTOR, css)
                if found and (found[0].text or "").strip():
                    html = found[0].get_attribute("outerHTML") or ""
                    text = html_to_text(html) or (found[0].text or "")
                    break
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
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
                detail_text=text or ("详情为PDF文件，请下载附件查看" if urls else ""),
                detail_html=html,
                file_urls=urls,
                project_code=row["project_code"],
                purchaser_hint="中国邮政",
                purchase_method_hint=row["method"],
                tender_end_time_hint=row["deadline"],
                biz_net=self.spec.net_name,
                industry_hint="交通运输",
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
