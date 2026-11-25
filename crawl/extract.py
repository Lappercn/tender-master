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
    date_part = r"(\d{4}年\d{1,2}月\d{1,2}日(?:\s*\d{1,2}(?:[:：]\d{1,2}|时(?:\d{1,2}分?)?))?)"
    patterns = [
        rf"(递交|提交).*?(截止时间|结束时间).*?{date_part}",
        rf"(投标|响应|报价|比选|申请文件).*?(截止时间|结束时间).*?{date_part}",
        rf"(开标时间|开启时间|开标).*?{date_part}",
        rf"(报名).*?(截止时间|结束时间).*?{date_part}",
        rf"{date_part}.*?截止",
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


_AREA_KEYWORDS = (
    ("北京", ("北京",)),
    ("天津", ("天津",)),
    ("上海", ("上海",)),
    ("重庆", ("重庆",)),
    ("广东", ("广东", "广州", "深圳", "佛山", "东莞", "珠海")),
    ("江苏", ("江苏", "南京", "苏州", "无锡", "常州")),
    ("浙江", ("浙江", "杭州", "宁波", "温州", "嘉兴")),
    ("山东", ("山东", "济南", "青岛", "烟台")),
    ("四川", ("四川", "成都", "绵阳")),
    ("湖北", ("湖北", "武汉", "宜昌")),
    ("湖南", ("湖南", "长沙")),
    ("河南", ("河南", "郑州")),
    ("河北", ("河北", "石家庄", "雄安", "唐山")),
    ("福建", ("福建", "福州", "厦门", "泉州")),
    ("安徽", ("安徽", "合肥")),
    ("江西", ("江西", "南昌")),
    ("陕西", ("陕西", "西安")),
    ("山西", ("山西", "太原")),
    ("辽宁", ("辽宁", "沈阳", "大连")),
    ("吉林", ("吉林", "长春")),
    ("黑龙江", ("黑龙江", "哈尔滨", "大庆")),
    ("广西", ("广西", "南宁", "柳州", "桂林")),
    ("云南", ("云南", "昆明")),
    ("贵州", ("贵州", "贵阳")),
    ("海南", ("海南", "海口", "三亚")),
    ("内蒙古", ("内蒙古", "呼和浩特", "包头", "鄂尔多斯")),
    ("甘肃", ("甘肃", "兰州")),
    ("青海", ("青海", "西宁")),
    ("宁夏", ("宁夏", "银川")),
    ("新疆", ("新疆", "乌鲁木齐")),
    ("西藏", ("西藏", "拉萨")),
    ("香港", ("香港",)),
    ("澳门", ("澳门",)),
    ("台湾", ("台湾",)),
)


def guess_area(source, title, purchaser):
    blob = f"{title or ''}{purchaser or ''}"
    for province, words in _AREA_KEYWORDS:
        if any(word in blob for word in words):
            return province
    if "南方电网" in (source or ""):
        return "南方电网覆盖区域"
    if "重庆" in (source or ""):
        return "重庆"
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
