"""沿用《字段提取逻辑说明》里的正则。先把原文存下来，不在这里加新的价格规则。"""
import re


def extract_budget(content):
    patterns = [
        r"(预算金额|预算总金额|项目预算).*?([\d,]+(\.\d+)?).*?(万|元)",
        r"(最高限价|最高限制单价|最高单价限价|限价|招标控制价|投标限价|最高投标限价).*?([\d,]+(\.\d+)?).*?(万|元)",
        r"(采购控制价|控制价).*?([\d,]+(\.\d+)?).*?(万|元)",
        r"(合同估算价|估算价|项目概算|概算金额|项目投资).*?([\d,]+(\.\d+)?).*?(万|元)",
        r"(资金来源|出资比例).*?([\d,]+(\.\d+)?).*?(万|元)",
        r"(单价|金额|价格).*?([\d,]+(\.\d+)?).*?(万|元)",
    ]
    for pattern in patterns:
        match = re.search(pattern, content or "")
        if match:
            return match.group(0), match.group(1)
    return None, None


def extract_end_time(content):
    patterns = [
        r"(递交|提交).*?(截止时间|结束时间).*?(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{1,2})?)",
        r"(投标|响应|报价|比选|申请文件).*?(截止时间|结束时间).*?(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{1,2})?)",
        r"(开标时间|开启时间|开标).*?(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{1,2})?)",
        r"(报名).*?(截止时间|结束时间).*?(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{1,2})?)",
        r"(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}:\d{1,2})?).*?截止",
    ]
    for pattern in patterns:
        match = re.search(pattern, content or "")
        if not match:
            continue
        for group in reversed(match.groups()):
            if group and re.search(r"\d{4}年", group):
                return group
    return None


def extract_contacts(content):
    contacts = []
    combo = r"(项目联系人|联系人|负责人|联系方式|技术咨询|商务咨询|异议联系人)[:：]\s*([\u4e00-\u9fa5]{2,4}).{0,50}?(联系电话|电话|手机)[:：]\s*([\d-]{8,})"
    found = False
    for match in re.finditer(combo, content or ""):
        found = True
        contacts.append({"name": match.group(2), "phone": match.group(4)})
    if found:
        return contacts
    name_match = re.search(r"(项目联系人|联系人|负责人|技术咨询|商务咨询|异议联系人)[：:]\s*([\u4e00-\u9fa5]{2,4})", content or "")
    phone_match = re.search(r"(联系电话|电话|手机|联系方式)[：:]\s*([\d-]{8,})", content or "")
    item = {}
    if name_match:
        item["name"] = name_match.group(2)
    if phone_match:
        item["phone"] = phone_match.group(2)
    if item:
        contacts.append(item)
    return contacts


def _value_after(patterns, content):
    for pattern in patterns:
        match = re.search(pattern, content or "")
        if not match:
            continue
        value = re.split(r"[\r\n]", match.group(2).strip())[0].strip()
        if len(value) > 80:
            value = value[:80]
        return value or None
    return None


def extract_purchaser(content):
    return _value_after([
        r"(采购人|采购单位|招标人|招标单位|需求单位|业主单位|建设单位|发包人|项目业主|招商人|采购单位名称)[：:]\s*(.+)",
        r"(采购人名称|招标人名称)[：:]\s*(.+)",
    ], content)


def extract_agent(content):
    return _value_after([
        r"(代理机构|招标代理|招标代理机构|采购代理|采购代理机构|代理单位|招标服务单位|比选代理机构)[：:]\s*(.+)",
        r"(代理机构名称)[：:]\s*(.+)",
    ], content)


def extract_purchase_method(content):
    return _value_after([
        r"(采购方式|招标方式|选取方式|运作方式)[：:]\s*(.+)",
        r"(项目类型)[：:]\s*(.+)",
    ], content)


def extract_winning(content):
    bidder = _value_after([
        r"(中标人|中标单位|成交人|成交供应商|成交单位|供应商名称|中标供应商|第一中标候选人|预中标单位|中标单位名称)[：:]\s*(.+)",
    ], content)
    amount = None
    match = re.search(r"(中标金额|中标价格|成交金额|成交价格|投标报价|中标价).*?([\d,]+(\.\d+)?).*?(万|元)", content or "")
    if match:
        amount = match.group(0)
    return bidder, amount


def classify_notice(title, channel_label=""):
    title = title or ""
    if "意见征集" in title or channel_label == "意见征集":
        return "意见征集"
    if "寻源" in title or channel_label == "寻源公告":
        return "寻源公告"
    if "流标" in title or channel_label == "流标公告":
        return "流标公告"
    if "中止" in title or "终止" in title:
        return "中止公告"
    if "变更" in title or "修改" in title or "更正" in title:
        return "更正公告"
    if "候选人" in title:
        return "中标候选人公示"
    if "废标" in title:
        return "废标公告"
    if "中标" in title or "成交" in title:
        return "中标公示" if "公示" in title else "中标公告"
    if "资格预审" in title or channel_label == "资格预审公告":
        return "资格预审公告"
    # 询比沿用原来的归类，仍记成招标公告。
    if "询比" in title:
        return "招标公告"
    if channel_label == "采购公告":
        return "采购公告"
    if channel_label == "非招标公告":
        return "非招标公告"
    if channel_label == "推荐中标候选人公示":
        return "中标候选人公示"
    if channel_label == "中标（成交）结果公告":
        return "中标公告"
    return "招标公告"


def guess_area(source, title, purchaser):
    blob = f"{title or ''}{purchaser or ''}"
    if "南方电网" in (source or ""):
        if any(word in blob for word in ("广东", "广州", "深圳")):
            return "广东"
        if "广西" in blob:
            return "广西"
        if "云南" in blob:
            return "云南"
        if "贵州" in blob:
            return "贵州"
        if "海南" in blob:
            return "海南"
        return "南方电网覆盖区域"
    if "重庆" in blob:
        return "重庆"
    if "北京" in blob:
        return "北京"
    return "全国"


def purchaser_from_title(title):
    match = re.search(r"【(.*?)】", title or "")
    if match:
        return match.group(1).strip() or None
    return None


def annex_names(content):
    return re.findall(
        r"附件\d*\s*[：:]\s*([^\s，,；;]+\.(?:pdf|docx?|xlsx?|zip|rar|7z))",
        content or "",
        flags=re.I,
    )
