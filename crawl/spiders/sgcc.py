"""国家电网。五个招标采购栏目都会翻页，详情里的表格和附件名一起留下。"""
import logging

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from collect.sources.sgcc_ecp.attachments import notice_id_from_url, resolve_attachments
from collect.sources.sgcc_ecp.constants import HOME_URL, LIST_ROW, MORE_BUTTON, TITLE_CELL
from collect.sources.sgcc_ecp.source import SOURCE
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


class SgccSpider:
    spec = SOURCE

    def run(self, job, store, profile):
        result = JobResult()
        with browser_session(profile, self.spec.id) as driver:
            page = Page(driver, job.pace)
            logger.info("打开 %s %s，范围 %s", self.spec.name, profile.describe(), label_of(job.span))
            driver.get(HOME_URL)
            page.human_gap("page")
            try:
                page.click_css(MORE_BUTTON)
                page.human_gap("page")
            except Exception as exc:
                result.status = "failed"
                result.error = f"打不开招标采购列表：{exc}"
                logger.exception(result.error)
                return result
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
        if result.saved == 0 and result.error and not result.channels:
            result.status = "failed"
        elif result.failed and result.saved == 0 and result.error:
            result.status = "failed"
        elif result.failed:
            result.status = "partial"
        return result

    def _crawl_channel(self, driver, page, job, store, channel_id, label, result):
        logger.info("栏目 %s", label)
        mark(store, self.spec, channel_id, label, 1, result, "正在打开栏目")
        self._open_menu(driver, page, label)
        start, end = window_bounds(job.lookback_hours)
        seen = 0
        while True:
            seen += 1
            if job.page_end and seen > job.page_end:
                mark(store, self.spec, channel_id, label, seen, result, "到达指定页")
                return "到达指定页"
            if seen > job.max_pages:
                mark(store, self.spec, channel_id, label, seen, result, "到达单次页数上限")
                return "到达单次页数上限"
            page.human_gap("page")
            try:
                page.wait_css(LIST_ROW)
            except Exception:
                mark(store, self.spec, channel_id, label, seen, result, "页面上没有列表")
                return "页面上没有列表"
            mark(store, self.spec, channel_id, label, seen, result, f"正在看第 {seen} 页")
            action = self._crawl_table(driver, page, job, store, channel_id, label, start, end, result)
            if action == "stop":
                mark(store, self.spec, channel_id, label, seen, result, "日期已早于采集范围")
                return "日期已早于采集范围"
            if not page.click_next():
                mark(store, self.spec, channel_id, label, seen, result, "没有下一页")
                return "没有下一页"

    def _open_menu(self, driver, page, label):
        before = _first_title(driver)
        css = f"a[title='{label}']"
        page.click_css(css)
        page.pause(0.8, 1.6)
        after = _first_title(driver)
        if before and after == before:
            element = driver.find_element(By.CSS_SELECTOR, css)
            ActionChains(driver).double_click(element).perform()
            page.pause(0.8, 1.6)

    def _crawl_table(self, driver, page, job, store, channel_id, label, start, end, result):
        rows = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
        for index in range(len(rows)):
            rows = driver.find_elements(By.CSS_SELECTOR, LIST_ROW)
            if index >= len(rows):
                break
            cells = rows[index].find_elements(By.TAG_NAME, "td")
            if len(cells) < 4:
                continue
            date_text = (cells[-1].text or "").strip()[:10]
            decision = judge_date(date_text, start, end)
            if decision == "stop":
                return "stop"
            if decision != "take":
                continue
            title = " ".join((cells[0].text or "").split())
            project_code = " ".join((cells[1].text or "").split())
            project_status = " ".join((cells[2].text or "").split())
            fingerprint = content_id(title)
            if not fingerprint:
                continue
            existing = store.find_notice(self.spec.id, fingerprint, date_text)
            if skip_as_duplicate(existing, fingerprint) and self._files_ready(store, existing, fingerprint, label, title, result):
                old_code = (existing or {}).get("projectCode")
                if old_code and project_code and old_code != project_code:
                    logger.warning("标题相同但项目编号不同，仍按标题跳过：%s | %s / %s", title, old_code, project_code)
                continue
            self._open_detail(
                driver, page, job, store, channel_id, label, title, fingerprint,
                date_text, project_code, project_status, result, start, end,
            )
        return "continue"

    def _open_detail(self, driver, page, job, store, channel_id, label, title, fingerprint,
                     date_text, project_code, project_status, result, start, end):
        main = driver.current_window_handle
        try:
            title_cell = None
            for row in driver.find_elements(By.CSS_SELECTOR, LIST_ROW):
                cell = row.find_elements(By.CSS_SELECTOR, TITLE_CELL)
                if cell and title in " ".join((cell[0].text or "").split()):
                    title_cell = cell[0]
                    break
            if title_cell is None:
                raise RuntimeError("列表里找不到这条标题")
            title_cell.click()
            page.pause(1.5, 3)
            page.wait.until(lambda item: len(item.window_handles) > 1)
            for handle in driver.window_handles:
                if handle != main:
                    driver.switch_to.window(handle)
                    break
            page.pause(1.5, 3)
            page.glance()
            text, html, names = read_detail(driver)
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("发布时间早于采集范围，跳过：%s", title)
                return
            found = resolve_attachments(driver.current_url)
            urls = found["urls"]
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
                site_notice_id=notice_id_from_url(driver.current_url),
                project_code=project_code,
                project_status=project_status,
                extra={"annexNames": names} if names else {},
            )
            saved = self._save_files(store, fingerprint, urls, found)
            doc["files"] = saved
            doc["hasAnnex"] = bool(urls or found.get("hasFile"))
            doc["script"] = self.spec.script
            outcome = store.save_notice(self.spec.id, doc)
            if outcome == "duplicate":
                store.attach_files(self.spec.id, fingerprint, saved, urls)
                result.skipped += 1
                step = "补附件"
            else:
                result.saved += 1
                step = "已保存"
            logger.info("%s", notice_line(label, step, title, file_note(saved, found.get("note"))))
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

    def _save_files(self, store, fingerprint, urls, found):
        if urls:
            return store_files(self.spec.net, self.spec.id, fingerprint, urls)
        if found.get("retry"):
            return [{"key": "", "name": "", "url": "", "path": "", "size": 0, "ok": False, "error": found.get("note") or "查询附件失败"}]
        return []


def _first_title(driver):
    try:
        return " ".join((driver.find_element(By.CSS_SELECTOR, TITLE_CELL).text or "").split())
    except Exception:
        return ""


_CONTENT = (
    "app-doc-spec #md",
    "app-doc-com #md",
    "app-doci-bid div.doc",
    "app-doci-change div.doc",
    "app-doci-delay div.doc",
    "app-doci-win div.doc",
    "app-doci-waste div.doc",
    "app-doci-single div.doc",
    "#md",
    "app-doci-change",
    "app-doci-delay",
    "app-doci-win",
    "app-doci-waste",
    "app-doci-single",
    "div.doc",
)


def read_detail(driver):
    """只收公告正文。导航、页脚、下载按钮和整页都不进正文，附件名单独记。"""
    names = []
    for anchor in driver.find_elements(By.CSS_SELECTOR, "app-downfile a"):
        name = " ".join((anchor.text or "").split())
        if name and name not in names:
            names.append(name)
    element = None
    for css in _CONTENT:
        found = driver.find_elements(By.CSS_SELECTOR, css)
        if found and (found[0].text or "").strip():
            element = found[0]
            break
    if element is None:
        return "", "", names
    html = element.get_attribute("outerHTML") or ""
    return html_to_text(html), html, names
