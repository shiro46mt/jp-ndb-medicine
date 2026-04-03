import re
from .constants import MEDICAL_CLASS_VALUES

def _search(keywords, text, default=''):
    """キーワードがテキストに含まれているかどうかをチェック"""
    found_keywords = [keyword for keyword in keywords if keyword in text] + [default]
    return found_keywords[0]

def _search_medical_class(text: str) -> str:
    """医療区分をテキストから抽出"""
    normalized = re.sub(r'\s*\(', '（', re.sub(r'\)', '）', text))
    return _search(MEDICAL_CLASS_VALUES, normalized)

def _exclude_total(df, method: str):
    """総計行を除外"""
    if method == '性年齢別':
        return df[df['性別'] != '総計']
    elif method == '都道府県別':
        return df[df['都道府県名'] != '総計']
    elif method == '診療月別':
        return df[df['診療月'] != '総計']
    return df
