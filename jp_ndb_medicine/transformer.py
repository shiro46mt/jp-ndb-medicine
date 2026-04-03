import re
from logging import getLogger

import numpy as np
import pandas as pd

from .constants import BASE_YEAR, INDEX_COLS
from .helpers import _search_medical_class, _exclude_total
from .models import FileInfo

logger = getLogger(__name__)

class NDBTransformer:
    """NDBデータの変換処理を担当"""

    @staticmethod
    def read_file(fileinfo: FileInfo, condition_medical_class=None, include_total: bool = False) -> pd.DataFrame:
        """Excelファイルを読み込み、縦持ちに変換"""
        # 読み込み
        data = {}
        if fileinfo.url.startswith('http'):
            logger.info(f"Downloading '{fileinfo}' from '{fileinfo.url}'")

        dfs = pd.read_excel(fileinfo.url, header=[2,3], sheet_name=None, dtype=str)

        for sheet_name, df in dfs.items():
            medical_class = _search_medical_class(sheet_name)
            data[medical_class] = df

        # シート単位で変換処理
        concat_df = pd.DataFrame()
        for medical_class, df in data.items():
            if condition_medical_class and medical_class not in condition_medical_class:
                continue

            df = NDBTransformer._transform(df, fileinfo, medical_class)

            # 総計行の除外
            if not include_total:
                df = _exclude_total(df, fileinfo.method)

            concat_df = pd.concat([concat_df, df], axis=0)

        return concat_df

    @staticmethod
    def _transform(df: pd.DataFrame, fileinfo: FileInfo, medical_class: str) -> pd.DataFrame:
        """DataFrame を縦持ちに変換"""
        # 列の追加：第2回まで、単位がないので空欄を代入
        if '単位' not in df.columns:
            df.insert(4, '単位', np.nan)

        # 列名の編集
        df.columns = INDEX_COLS + [('総計', '総計')] + df.columns.to_list()[len(INDEX_COLS)+1:]

        # nan埋め
        df[['薬効分類','薬効分類名称']] = df[['薬効分類','薬効分類名称']].ffill()

        # 縦持ちに変換
        df = (
            df.set_index(INDEX_COLS)
            .stack()
            .reset_index()
        )
        df.columns = INDEX_COLS + ['集計単位', '処方数量']

        # 集計方法ごとの処理: 性年齢別
        if fileinfo.method == '性年齢別':
            df[['性別', '年齢区間']] = df['集計単位'].to_list()

            # 性別の表記揺らぎを矯正
            df['性別'] = df['性別'].str.replace('性', '')

            # 年齢下限の追加
            def ufunc(s):
                if s == '総計':
                    return -1
                return int(re.search(r"^\d+", s).group(0))
            df = df.assign(年齢 = lambda d: d['年齢区間'].apply(ufunc))

            df = df[INDEX_COLS + ['性別', '年齢', '年齢区間', '処方数量']]

        # 集計方法ごとの処理: 都道府県別
        elif fileinfo.method == '都道府県別':
            df[['都道府県コード', '都道府県名']] = df['集計単位'].to_list()

            # 総計行の都道府県コードの編集
            df['都道府県コード'] = df['都道府県コード'].mask(df['都道府県コード'] == '総計', '00')

            df = df[INDEX_COLS + ['都道府県コード', '都道府県名', '処方数量']]

        # 集計方法ごとの処理: 診療月別
        elif fileinfo.method == '診療月別':
            df[['診療月', '診療年月']] = df['集計単位'].to_list()

            # 診療年月の設定
            def ufunc(month):
                if month == '総計':
                    return '総計'
                year = fileinfo.nth + BASE_YEAR
                month = int(month[:-1])
                if month < 4:
                    return f'{year+1:0>4d}/{month:0>2d}'
                else:
                    return f'{year:0>4d}/{month:0>2d}'
            df['診療年月'] = df['診療月'].apply(ufunc)

            df = df[INDEX_COLS + ['診療月', '診療年月', '処方数量']]

        # 最小集計単位未満のセルの置換
        df['最小集計単位未満'] = (df['処方数量'] == '-').astype(np.int8)
        df['処方数量'] = df['処方数量'].mask(df['処方数量'] == '-').fillna('0')

        # 列の追加
        cols = df.columns.to_list()
        df['実施回'] = fileinfo.nth
        df['年度'] = fileinfo.nth + BASE_YEAR
        df['剤形'] = fileinfo.dosage
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
