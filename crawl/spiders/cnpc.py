"""中国石油电子招标投标交易平台。招标公告与中标结果模块公开栏目采集。"""
import logging

from selenium.webdriver.common.by import By

from collect.sources.cnpc_bid.constants import DETAIL_BOX, HOME_URL, LIST_ROW, MODULE_URLS
from collect.sources.cnpc_bid.source import SOURCE
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


class CnpcSpider:
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
        target_url = MODULE_URLS.get(channel_id, f"{HOME_URL}/#/tenders")
        driver.get(target_url)
        page.human_gap("page")
        if self._has_captcha(driver):
            mark(store, self.spec, channel_id, label, 1, result, "站点弹出安全验证，已暂停访问")
            return "站点弹出安全验证"
        self._select_tab(driver, page, label)
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
            if self._has_captcha(driver):
                mark(store, self.spec, channel_id, label, page_no, result, "站点弹出安全验证，已暂停访问")
                return "站点弹出安全验证"
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
            if not page.click_next():
                mark(store, self.spec, channel_id, label, page_no, result, "没有下一页")
                return "没有下一页"
            page.human_gap("page")

    def _has_captcha(self, driver):
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[placeholder='验证码']")
        return any(item.is_displayed() for item in inputs)

    def _select_tab(self, driver, page, label):
        try:
            tab = driver.find_element(By.XPATH, f"//ul[contains(@class,'el-menu')]//li//span[contains(text(),'{label}')]")
            parent_li = tab.find_element(By.XPATH, "./..")
            if "is-active" not in (parent_li.get_attribute("class") or ""):
                driver.execute_script("arguments[0].click();", tab)
                page.human_gap("page")
        except Exception:
            pass

    def _read_rows(self, driver):
        rows = []
        for row in driver.find_elements(By.CSS_SELECTOR, LIST_ROW):
            try:
                title = (row.find_element(By.CSS_SELECTOR, "div.contant").text or "").strip()
                date_text = (row.find_element(By.XPATH, "./div[last()]").text or "").strip()[:10]
                if title:
                    rows.append({"title": " ".join(title.split()), "date": date_text})
            except Exception:
                continue
        return rows

    def _take_row(self, driver, page, job, store, channel_id, label, row, result, start, end):
        title = row["title"]
        fingerprint = content_id(title)
        if not fingerprint:
            return
        existing = store.find_notice(self.spec.id, fingerprint, row["date"])
        if skip_as_duplicate(existing, fingerprint) and files_settled(existing):
            result.skipped += 1
            logger.info("%s", notice_line(label, "跳过", title, "附件已齐"))
            return
        main = driver.current_window_handle
        try:
            target = None
            for elem in driver.find_elements(By.CSS_SELECTOR, "div.box_data div.contant"):
                if title in " ".join((elem.text or "").split()):
                    target = elem
                    break
            if target is None:
                return
            driver.execute_script("arguments[0].click();", target)
            page.pause(1.5, 3.0)
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
            page.wait_css(DETAIL_BOX)
            page.glance()
            box = driver.find_element(By.CSS_SELECTOR, DETAIL_BOX)
            html = box.get_attribute("outerHTML") or ""
            text = html_to_text(html) or (box.text or "")
            if outside_detail(text, start, end, job.lookback_hours):
                result.skipped += 1
                logger.info("%s", notice_line(label, "跳过", title, "发布时间早于采集范围"))
                return
            annex_names = []
            for div in driver.find_elements(By.XPATH, "//div[contains(@class,'cursor_style')]"):
                name = (div.text or "").replace("附件：", "").replace("附件:", "").strip()
                if name and name not in annex_names:
                    annex_names.append(name)
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
                file_urls=[],
                biz_net=self.spec.net_name,
                industry_hint="石油化工",
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
                try:
                    back = driver.find_element(By.XPATH, "//button[contains(@class,'footer')]//span[contains(text(),'返回')]/..")
                    driver.execute_script("arguments[0].click();", back)
                except Exception:
                    driver.back()
            page.human_gap("detail")
