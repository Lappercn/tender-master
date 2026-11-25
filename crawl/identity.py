"""标题指纹。去重看清洗后的标题，不单看站点给的编号。"""
import hashlib
import re


def clean_title(title):
    """去掉空格和括号、连字符，再转小写。同一条公告换一种标点仍能对上。"""
    if not title:
        return ""
    text = title.strip()
    text = re.sub(r"[【】\[\]（）\-]", "", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def content_id(title):
    cleaned = clean_title(title)
    if not cleaned:
        return ""
    return hashlib.md5(cleaned.encode("utf-8")).hexdigest()


def skip_as_duplicate(existing, new_content_id):
    """只有标题指纹相同才跳过。编号相同但标题不同，保留。"""
    if not existing or not new_content_id:
        return False
    return existing.get("contentId") == new_content_id
