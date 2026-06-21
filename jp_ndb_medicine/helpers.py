from logging import Logger
from pathlib import Path
import re
from typing import Optional

from .constants import MEDICAL_CLASS_VALUES, FILENAME_PATTERN
from .models import FileInfo

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

def _parse_to_fileinfo(filepath: Path, logger: Logger) -> Optional[FileInfo]:
    """ファイル名から FileInfo を抽出"""
    pattern = rf"{FILENAME_PATTERN}"
    mob = re.match(pattern, filepath.stem)

    # TODO: 第10回以降のZIPファイルの命名規則に対応する必要がある
    if mob:
        try:
            nth = int(mob.group(1)) if mob.group(1) else None
            dosage = mob.group(2)
            medical_class = mob.group(3)
            method = mob.group(4)
            public_fund = mob.group(6) == '(公費含む)'

            return FileInfo(
                url=str(filepath.resolve()),
                nth=nth,
                public_fund=public_fund,
                dosage=dosage,
                medical_class=medical_class,
                method=method,
            )
        except (IndexError, ValueError) as e:
            logger.warning(f'ファイル名の解析に失敗: {e}')
            return None

    return None
