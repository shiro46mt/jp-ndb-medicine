from logging import getLogger
import os
from pathlib import Path
import re
import time
from typing import Union, Literal, List, NamedTuple

from bs4 import BeautifulSoup
import numpy as np
import pandas as pd
import requests
from tqdm import tqdm

# ログ設定
logger = getLogger(__name__)

# 【NDB】NDBオープンデータURL
domain_mhlw = 'https://www.mhlw.go.jp'
url_top = "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177182.html"

# requests用パラメータ
headers = {'User-Agent': ''}
timeout_sec = 60
interval_sec = 0.1


def _search(keywords, text, default=''):
    # キーワードがテキストに含まれているかどうかをチェックし、含まれているキーワードをリストに追加
    found_keywords = [keyword for keyword in keywords if keyword in text] + [default]
    return found_keywords[0]


class _FileLink(NamedTuple):
    nth: int
    dosage: str
    medical_class: str
    method: str
    url: str

    def __str__(self):
        return f"{self.nth:0>2d}_{self.dosage}_{self.medical_class}_{self.method}"


class NDBMedicine:
    dosage_values = ('内服', '外用', '注射', '歯科用薬剤')
    medical_class_values = ('外来（院内）', '外来（院外）', '入院')
    medical_class_default_value = ''
    method_values = ('性年齢別', '都道府県別')
    index_cols = ['薬効分類', '薬効分類名称', '医薬品コード', '医薬品名', '単位', '薬価基準収載医薬品コード', '薬価', '後発品区分']

    def __init__(self):
        self.page_links = dict()
        self.file_links = []
        # 各回のページへのリンク
        try:
            self._get_page_links()
        except:
            logger.warning('NDBオープンデータのページにアクセスできません。')
        # Excelファイルのリンク
        for nth in self.page_links:
            self._get_file_links(nth)
            time.sleep(interval_sec)

    #
    # 厚労省HPのスクレイピング
    #
    def _get_page_links(self):
        """各回のページへのリンクを取得"""
        r = requests.get(url_top, headers=headers, timeout=timeout_sec)
        if r.status_code != 200:
            raise Exception(r.status_code)

        string_pattern = re.compile(r'第(\d+)回NDBオープンデータ')
        soup = BeautifulSoup(r.content, "html.parser")
        tags = soup.find_all('a', string=string_pattern)
        for tag in tags:
            n = int(string_pattern.match(tag.text).group(1))
            link = tag.attrs['href']
            if link.startswith('/'):
                link = domain_mhlw + link
            self.page_links[n] = link

    def _get_file_links(self, nth: int):
        """Excelファイルのリンクを取得"""
        assert nth in self.page_links

        page_url = self.page_links[nth]
        r = requests.get(page_url, headers=headers, timeout=timeout_sec)
        if r.status_code != 200:
            raise Exception(r.status_code)

        soup = BeautifulSoup(r.content, "html.parser")
        h3_tag = soup.find('h3', string=re.compile('処方薬|薬剤'))
        assert h3_tag is not None

        section = ''
        for tag in h3_tag.find_all_next(['h3', 'h4', 'a']):
            # 次のh3タグに到達したら終了
            if tag.name == 'h3':
                break
            # h4タグがあれば、セクションの始まりとする
            elif tag.name == 'h4':
                section = tag.text.strip()
            # aタグで、テキストが条件に一致する場合の処理
            elif '薬効分類別数量' in tag.text:
                name = tag.text
                # 剤形
                if section in self.dosage_values:
                    dosage = section
                elif section == '歯科' and '歯科用薬剤' in name:
                    dosage = '歯科用薬剤'
                elif section == '' and name[:2] in self.dosage_values:  # 第1回の対応
                    dosage = name[:2]
                else:  # 医科、または歯科の内服の場合はスキップ
                    continue

                # 診療区分
                medical_class = _search(self.medical_class_values, name, default=self.medical_class_default_value)

                # 集計方法
                method = _search(self.method_values, name)

                link = tag.attrs['href']
                if link.startswith('/'):
                    link = domain_mhlw + link
                self.file_links.append(
                    _FileLink(nth, dosage, medical_class, method, link))

    def _get_file(self, file_link: _FileLink, save_dir: Union[str, os.PathLike]) -> Path:
        """download_urlのファイルをダウンロード -> ファイルを保存 -> ファイルパスを返す"""
        # 保存先フォルダ
        if isinstance(save_dir, str):
            save_dir = Path(save_dir)

        if not isinstance(save_dir, Path) or not save_dir.is_dir():
            raise FileNotFoundError("No such directory: '%s'", save_dir)

        # ダウンロードファイルの名前
        filename = f"{file_link}.xlsx"
        filepath = save_dir / filename

        # ファイルダウンロード
        logger.info(f"Downloading '{filename}' from '{file_link.url}'")
        r = requests.get(file_link.url, stream=True)
        with open(filepath, 'wb') as zf:
            zf.write(r.content)

        return filepath

    #
    # Excelファイルのデータの読み込み・変換
    #
    def _read_file(self, file_link: _FileLink, condition_medical_class=None, include_total: bool = False) -> pd.DataFrame:
        """対象ファイルを厚労省HPから読み込み -> 縦持ちに変換"""
        # 読み込み
        data = {}
        if file_link.url.startswith('http'):
            logger.info(f"Downloading '{file_link}' from '{file_link.url}'")
        dfs = pd.read_excel(file_link.url, header=[2,3], sheet_name=None, dtype=str)
        for sheet_name, df in dfs.items():
            medical_class = _search(self.medical_class_values, re.sub(r'\s*\(', '（', re.sub(r'\)', '）', sheet_name)))
            data[medical_class] = df

        # シート単位で変換処理
        concat_df = pd.DataFrame()
        for medical_class, df in data.items():
            if condition_medical_class and medical_class not in condition_medical_class:
                continue

            df = self._transform(df, file_link, medical_class)

            # 総計行の除外
            if not include_total:
                if file_link.method == '性年齢別':
                    df = df[df['性別'] != '総計']
                elif file_link.method == '都道府県別':
                    df = df[df['都道府県名'] != '総計']

            concat_df = pd.concat([concat_df, df], axis=0)

        return concat_df

    def _transform(self, df: pd.DataFrame, file_link: _FileLink, medical_class: str) -> pd.DataFrame:
        # 列の追加：第2回まで、単位がないので空欄を代入
        if '単位' not in df.columns:
            df.insert(4, '単位', np.nan)

        # 列名の編集
        df.columns = self.index_cols + [('総計', '総計')] + df.columns.to_list()[len(self.index_cols)+1:]

        # nan埋め
        df[['薬効分類','薬効分類名称']] = df[['薬効分類','薬効分類名称']].ffill()

        # 縦持ちに変換
        df = (
            df.set_index(self.index_cols)
            .stack()
            .reset_index()
        )
        df.columns = self.index_cols + ['集計単位', '処方数量']

        # 集計方法ごとの処理: 性年齢別
        if file_link.method == '性年齢別':
            df[['性別', '年齢区間']] = df['集計単位'].to_list()

            # 性別の表記揺らぎを矯正
            df['性別'] = df['性別'].str.replace('性', '')

            # 年齢下限の追加
            def ufunc(s):
                if s == '総計':
                    return -1
                return int(re.search(r"^\d+", s).group(0))
            df = df.assign(年齢 = lambda d: d['年齢区間'].apply(ufunc))

            df = df[self.index_cols + ['性別', '年齢', '年齢区間', '処方数量']]

        # 集計方法ごとの処理: 都道府県別
        elif file_link.method == '都道府県別':
            df[['都道府県コード', '都道府県名']] = df['集計単位'].to_list()

            # 総計行の都道府県コードの編集
            df['都道府県コード'] = df['都道府県コード'].mask(df['都道府県コード'] == '総計', '00')

            df = df[self.index_cols + ['都道府県コード', '都道府県名', '処方数量']]

        # 最小集計単位未満のセルの置換
        df['最小集計単位未満'] = (df['処方数量'] == '-').astype(np.int8)
        df['処方数量'] = df['処方数量'].mask(df['処方数量'] == '-').fillna('0')

        # 列の追加
        cols = df.columns.to_list()
        df['実施回'] = file_link.nth
        df['年度'] = file_link.nth + 2013
        df['剤形'] = file_link.dosage
        df['診療区分'] = medical_class
        df = df[['実施回', '年度', '剤形', '診療区分'] + cols]

        # データ型の変換
        df = df.astype({
            '実施回': np.int8,
            '年度': np.int16,
            '後発品区分': np.int8,
            '薬価': float,
            '処方数量': float,
        })

        return df

    #
    # メイン処理の内部関数
    #
    def _filter_file_links(self, nth, year, dosage, medical_class, method):
        file_links = [f for f in self.file_links]

        if nth:
            if isinstance(nth, int):
                file_links = [f for f in file_links if f.nth == nth]
            else:
                file_links = [f for f in file_links if f.nth in nth]

        elif year:
            if isinstance(year, int):
                file_links = [f for f in file_links if f.nth == year - 2013]
            else:
                nths = [y - 2013 for y in year]
                file_links = [f for f in file_links if f.nth in nths]

        if dosage:
            if isinstance(dosage, str):
                file_links = [f for f in file_links if f.dosage == dosage]
            else:
                file_links = [f for f in file_links if f.dosage in dosage]

        if medical_class:
            if isinstance(medical_class, str):
                file_links = [f for f in file_links if (f.medical_class == medical_class) or (f.medical_class == self.medical_class_default_value)]
            else:
                file_links = [f for f in file_links if (f.medical_class in medical_class) or (f.medical_class == self.medical_class_default_value)]

        if method:
            if isinstance(method, str):
                file_links = [f for f in file_links if f.method == method]
            else:
                file_links = [f for f in file_links if f.method in method]

        return file_links

    def _load(
            self,
            method: Literal['性年齢別', '都道府県別'],
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar=True) -> pd.DataFrame:
        """厚労省HPから、NDBオープンデータの処方薬のExcelファイルをダウンロードして読み込み、縦持ちに変換する。
            抽出条件は単一の値または複数の配列で指定可能。
            例）`nth=1` , `nth=[1,2,3]`

        Args:
            method: 集計方法。1つのみ指定する。
            nth: 実施回。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total (bool, Defaults `False`): `True`の場合、成分ごとの総計行を含める。
                総計行では便宜上、`年齢`=-1、`都道府県コード`='00'としている。
                ※総計行は元データの総計の列の値を使用しており、最小集計単位未満の値も含まれるため明細の単純合計と一致しない場合がある。
            progress_bar (bool, Defaults `True`): `True`の場合、ダウンロードの進捗状況を表示する。

        Return:
            `pd.DataFrame`
        """
        assert method in ['性年齢別', '都道府県別']
        file_links = self._filter_file_links(nth, year, dosage, medical_class, method)

        download_df = []
        for file_link in tqdm(file_links, desc='Downloading...', disable=not progress_bar):
            df = self._read_file(file_link, condition_medical_class=medical_class, include_total=include_total)
            download_df.append(df)

        return pd.concat(download_df, axis=0)

    #
    # メイン処理
    #
    def load_age(
            self,
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar=True,
        ) -> pd.DataFrame:
        """厚労省HPから、NDBオープンデータの処方薬のExcelファイル【性年齢別】をダウンロードして読み込み、縦持ちに変換する。
            抽出条件は単一の値または複数の配列で指定可能。
            例）`nth=1` , `nth=[1,2,3]`

        Args:
            nth: 実施回。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total (bool, Defaults `False`): `True`の場合、成分ごとの総計行を含める。
                総計行では便宜上 `年齢`=-1、`都道府県コード`='00'としている。
                ※総計行は元データの総計の列の値を使用しており、最小集計単位未満の値も含まれるため明細の単純合計と一致しない場合がある。
            progress_bar (bool, Defaults `True`): `True`の場合、ダウンロードの進捗状況を表示する。

        Return:
            `pd.DataFrame`
        """
        return self._load('性年齢別', nth=nth, year=year, dosage=dosage, medical_class=medical_class, include_total=include_total, progress_bar=progress_bar)

    def load_pref(
            self,
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar=True,
        ) -> pd.DataFrame:
        """厚労省HPから、NDBオープンデータの処方薬のExcelファイル【都道府県別】をダウンロードして読み込み、縦持ちに変換する。
            抽出条件は単一の値または複数の配列で指定可能。
            例）`nth=1` , `nth=[1,2,3]`

        Args:
            nth: 実施回。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total (bool, Defaults `False`): `True`の場合、成分ごとの総計行を含める。
                総計行では便宜上、`年齢`=-1、`都道府県コード`='00'としている。
                ※総計行は元データの総計の列の値を使用しており、最小集計単位未満の値も含まれるため明細の単純合計と一致しない場合がある。
            progress_bar (bool, Defaults `True`): `True`の場合、ダウンロードの進捗状況を表示する。

        Return:
            `pd.DataFrame`
        """
        return self._load('都道府県別', nth=nth, year=year, dosage=dosage, medical_class=medical_class, include_total=include_total, progress_bar=progress_bar)

    def save(
            self,
            save_dir: Union[str, os.PathLike],
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            method: Union[Literal['性年齢別', '都道府県別'], List[Literal['性年齢別', '都道府県別']], None] = None,
            progress_bar=True) -> List[str]:
        """厚労省HPから、NDBオープンデータの処方薬のExcelファイルをダウンロードして保存する。
            抽出条件は単一の値または複数の配列で指定可能。
            例）`nth=1` , `nth=[1,2,3]`

        Args:
            save_dir: 保存先フォルダ。
            nth: 実施回。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            method: 集計方法。
            progress_bar (bool, Defaults `True`): `True`の場合、ダウンロードの進捗状況を表示する。

        Return:
            保存先ファイルパス (str) のリスト
        """
        file_links = self._filter_file_links(nth, year, dosage, medical_class, method)

        download_files = []
        for file_link in tqdm(file_links, desc='Downloading...', disable=not progress_bar):
            filepath = self._get_file(file_link, save_dir)
            download_files.append(str(filepath))
            time.sleep(interval_sec)

        return download_files

    def read_excel(
            self,
            filepath: Union[str, os.PathLike],
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            *,
            include_total: bool = False,
        )  -> pd.DataFrame:
        """ローカルに保存されたNDBオープンデータの処方薬のExcelファイルを読み込み、縦持ちに変換する。
            抽出条件は単一の値または複数の配列で指定可能。
            例）`nth=1` , `nth=[1,2,3]`

        Args:
            filepath: 読み込み元のExcelファイル。ファイル名は`"{nth}_{dosage}_{medical_class}_{method}.xlsx"` の形式が必要。
            medical_class: 診療区分。単一の値または複数の配列で指定可能。指定しない場合、すべてのシートを読み込む。
            include_total (bool, Defaults `False`): `True`の場合、成分ごとの総計行を含める。
                総計行では便宜上、`年齢`=-1、`都道府県コード`='00'としている。
                ※総計行は元データの総計の列の値を使用しており、最小集計単位未満の値も含まれるため明細の単純合計と一致しない場合がある。

        Return:
            `pd.DataFrame`
        """
        # 読み込み元ファイル
        if isinstance(filepath, str):
            filepath = Path(filepath)

        if not isinstance(filepath, Path) or not filepath.parent.is_dir():
            raise FileNotFoundError("No such directory: '%s'", filepath.parent)

        # ファイル名の解析
        nth, dosage, medical_class_, method = filepath.stem.split('_')
        assert int(nth) > 0, f"ファイル名が不正です。'{filepath.name}'"
        assert dosage in self.dosage_values, f"ファイル名が不正です。'{filepath.name}'"
        assert (medical_class_ in self.medical_class_values) or (medical_class_ == ''), f"ファイル名が不正です。'{filepath.name}'"
        assert method in self.method_values, f"ファイル名が不正です。'{filepath.name}'"

        file_link = _FileLink(int(nth), dosage, medical_class_, method, url=str(filepath))

        # ファイルの読み込み
        return self._read_file(file_link, condition_medical_class=medical_class, include_total=include_total)
