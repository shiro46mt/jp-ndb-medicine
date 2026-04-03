from logging import getLogger
import re
import time
from typing import Dict, List
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from .constants import (
    DOMAIN_MHLW, URL_TOP, HEADERS, TIMEOUT_SEC, INTERVAL_SEC,
    NTH_PATTERN, DOSAGE_VALUES, METHOD_VALUES, MEDICAL_CLASS_VALUES, MEDICAL_CLASS_DEFAULT_VALUE
)
from .models import FileInfo
from .helpers import _search

logger = getLogger(__name__)

class NDBScraper:
    """厚労省HPのスクレイピング処理を担当"""

    def __init__(self):
        self.page_links: Dict[int, str] = {}
        self.fileinfo_list: List[FileInfo] = []

    def fetch_all(self) -> List[FileInfo]:
        """ページリンクとファイル情報を取得"""
        try:
            self._get_page_links()
        except Exception as e:
            logger.warning(f'NDBオープンデータのページにアクセスできません: {e}')

        for nth in self.page_links:
            try:
                self._get_fileinfos(nth)
            except Exception as e:
                logger.warning(f'第{nth}回のファイル情報取得に失敗: {e}')
            time.sleep(INTERVAL_SEC)

        return self.fileinfo_list

    def _get_page_links(self) -> None:
        """各回のページへのリンクを取得"""
        try:
            r = requests.get(URL_TOP, headers=HEADERS, timeout=TIMEOUT_SEC)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.error(f'NDBオープンデータのページにアクセスできません: {e}')
            raise

        soup = BeautifulSoup(r.content, "html.parser")
        tags = soup.find_all('a', string=NTH_PATTERN)

        for tag in tags:
            try:
                n = int(NTH_PATTERN.match(tag.text).group(1))
                link = urljoin(DOMAIN_MHLW, tag.attrs['href'])
                self.page_links[n] = link
            except (ValueError, KeyError, AttributeError) as e:
                logger.warning(f'ページリンクの解析に失敗: {e}')

    def _get_fileinfos(self, nth: int) -> None:
        """Excelファイルのリンクを取得"""
        if nth not in self.page_links:
            raise ValueError(f"Invalid nth value: {nth}")

        page_url = self.page_links[nth]
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT_SEC)
            r.raise_for_status()
        except requests.RequestException as e:
            logger.error(f'第{nth}回ページの取得に失敗: {e}')
            raise

        soup = BeautifulSoup(r.content, "html.parser")
        h3_tag = soup.find('h3', string=re.compile('処方薬|薬剤'))

        if h3_tag is None:
            raise ValueError("Could not find h3 tag with expected content")

        section = ''
        for tag in h3_tag.find_all_next(['h3', 'h4', 'a']):
            if tag.name == 'h3':
                break
            elif tag.name == 'h4':
                section = tag.text.strip()
            elif '薬効分類別数量' in tag.text:
                self._process_link(tag, section, nth)

    def _process_link(self, tag, section: str, nth: int) -> None:
        """aタグから FileInfo を抽出"""
        name = tag.text

        # 剤形の判定
        if section in DOSAGE_VALUES:
            dosage = section
        elif section == '歯科' and '歯科用薬剤' in name:
            dosage = '歯科用薬剤'
        elif section == '' and name[:2] in DOSAGE_VALUES:
            dosage = name[:2]
        else:
            return

        # 診療区分と集計方法
        medical_class = _search(MEDICAL_CLASS_VALUES, name, default=MEDICAL_CLASS_DEFAULT_VALUE)
        method = _search(METHOD_VALUES, name)

        link = urljoin(DOMAIN_MHLW, tag.attrs['href'])
        self.fileinfo_list.append(
            FileInfo(nth, dosage, medical_class, method, link)
        )
