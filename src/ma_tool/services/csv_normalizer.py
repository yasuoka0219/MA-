"""CSV normalization utilities for robust import handling"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple


COLUMN_ALIASES: Dict[str, List[str]] = {
    "external_id": ["external_id", "externalid", "個人id", "個人ID", "学生id", "学生ID", "student_id", "studentid", "id"],
    "email": ["email", "mail", "メール", "メールアドレス", "eメール", "mailaddress", "emailaddress", "メールアドレス1", "メールアドレス2"],
    "email1": ["メールアドレス1", "email1", "mail1", "メール1", "email_1"],
    "email2": ["メールアドレス2", "email2", "mail2", "メール2", "email_2"],
    "name": ["name", "名前", "氏名", "姓名", "fullname", "フルネーム", "漢字氏名"],
    "school_name": ["school_name", "schoolname", "school", "学校", "学校名", "高校", "高校名", "出身校", "高校正式名称"],
    "graduation_year": ["graduation_year", "graduationyear", "卒業年", "卒業年度", "卒年", "grad_year", "gradyear"],
    "grade_label": ["grade_label", "gradelabel", "grade", "学年", "year", "年次"],
    "interest_tags": ["interest_tags", "interesttags", "interest", "興味", "関心", "志望", "志望学部", "tags", "タグ"],
    "consent": ["consent", "同意", "承諾", "許可", "オプトイン", "optin", "opt_in", "agree", "agreed"],
}


GRADE_LABEL_MAP: Dict[str, int] = {
    "高1": 1, "高2": 2, "高3": 3,
    "高一": 1, "高二": 2, "高三": 3,
    "1": 1, "2": 2, "3": 3,
    "１": 1, "２": 2, "３": 3,
    "1年": 1, "2年": 2, "3年": 3,
    "１年": 1, "２年": 2, "３年": 3,
    "高校1年": 1, "高校2年": 2, "高校3年": 3,
    "高校１年": 1, "高校２年": 2, "高校３年": 3,
    "高校1年生": 1, "高校2年生": 2, "高校3年生": 3,
    "高校１年生": 1, "高校２年生": 2, "高校３年生": 3,
    "1年生": 1, "2年生": 2, "3年生": 3,
    "１年生": 1, "２年生": 2, "３年生": 3,
    "一年": 1, "二年": 2, "三年": 3,
    "一年生": 1, "二年生": 2, "三年生": 3,
}


CONSENT_TRUE_VALUES = {
    "true", "1", "yes", "ok", "はい", "同意", "同意あり", "済", "済み", 
    "あり", "する", "承諾", "許可", "○", "◯", "o", "〇", "可"
}

CONSENT_FALSE_VALUES = {
    "false", "0", "no", "いいえ", "同意なし", "なし", "しない", 
    "不許可", "×", "x", "不可", "拒否"
}


def normalize_to_halfwidth(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalize_column_name(name: str) -> str:
    normalized = normalize_to_halfwidth(name)
    normalized = normalized.lower()
    normalized = re.sub(r'[\s\-_\.]+', '', normalized)
    normalized = re.sub(r'[^\w\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', '', normalized)
    return normalized


def map_column_name(raw_name: str) -> Tuple[Optional[str], float]:
    normalized = normalize_column_name(raw_name)
    
    for canonical, aliases in COLUMN_ALIASES.items():
        normalized_aliases = [normalize_column_name(a) for a in aliases]
        if normalized in normalized_aliases:
            return canonical, 1.0
    
    for canonical, aliases in COLUMN_ALIASES.items():
        normalized_aliases = [normalize_column_name(a) for a in aliases]
        for alias in normalized_aliases:
            if normalized in alias or alias in normalized:
                return canonical, 0.8
    
    return None, 0.0


def auto_map_columns(headers: List[str]) -> Dict[str, str]:
    mapping = {}
    for header in headers:
        canonical, confidence = map_column_name(header)
        if canonical and confidence > 0:
            mapping[header] = canonical
    return mapping


def normalize_email(email: str) -> str:
    email = normalize_to_halfwidth(email)
    email = email.strip().lower()
    email = email.replace('＠', '@')
    email = email.replace('．', '.')
    email = email.replace('。', '.')
    return email


def normalize_grade_label(label: str) -> Optional[int]:
    label = normalize_to_halfwidth(label).strip()
    
    if label in GRADE_LABEL_MAP:
        return GRADE_LABEL_MAP[label]
    
    normalized = re.sub(r'[^\d\u4e00-\u9fff]', '', label)
    if normalized in GRADE_LABEL_MAP:
        return GRADE_LABEL_MAP[normalized]
    
    match = re.search(r'[1-3１-３一二三]', label)
    if match:
        char = match.group()
        if char in '1１一':
            return 1
        elif char in '2２二':
            return 2
        elif char in '3３三':
            return 3
    
    return None


def normalize_consent(value: str) -> Tuple[Optional[bool], bool]:
    value = normalize_to_halfwidth(value).strip().lower()
    
    if value in CONSENT_TRUE_VALUES:
        return True, False
    if value in CONSENT_FALSE_VALUES:
        return False, False
    
    return None, True


def normalize_name(name: str) -> str:
    return normalize_to_halfwidth(name).strip()


def normalize_text(text: str) -> str:
    return normalize_to_halfwidth(text).strip()
