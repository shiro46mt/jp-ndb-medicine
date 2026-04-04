import os
import re
from logging import getLogger
from pathlib import Path
from typing import Optional, Union, Literal, List

import pandas as pd
from tqdm import tqdm

from .constants import (
    BASE_YEAR, TIMEOUT_SEC, METHOD_VALUES,
    MEDICAL_CLASS_DEFAULT_VALUE, FILENAME_PATTERN
)
from .models import FileInfo
from .scraper import NDBScraper
from .transformer import NDBTransformer

logger = getLogger(__name__)


class NDBMedicine:
    """NDBオープンデータの処方薬情報を取得・変換するメインクラス"""

    def __init__(self):
        """初期化：スクレイパーでファイル情報を取得"""
        self.scraper = NDBScraper()
        self.transformer = NDBTransformer()
        self.fileinfo_list: List[FileInfo] = []

        try:
            self.fileinfo_list = self.scraper.fetch_all()
            logger.info(f'ファイル情報を取得しました: {len(self.fileinfo_list)}件')
        except Exception as e:
            logger.warning(f'NDBオープンデータのページにアクセスできません: {e}')

    #
    # ファイルダウンロード・保存
    #
    def _get_file(self, fileinfo: FileInfo, save_dir: Union[str, os.PathLike]) -> Path:
        """URLのファイルをダウンロードして保存"""
        if isinstance(save_dir, str):
            save_dir = Path(save_dir)

        if not isinstance(save_dir, Path) or not save_dir.is_dir():
            raise FileNotFoundError(f"No such directory: '{save_dir}'")

        filename = f"{fileinfo}.xlsx"
        filepath = save_dir / filename

        try:
            logger.info(f"Downloading '{filename}' from '{fileinfo.url}'")
            r = __import__('requests').get(fileinfo.url, timeout=TIMEOUT_SEC)
            r.raise_for_status()

            with open(filepath, 'wb') as f:
                f.write(r.content)

            logger.info(f"Successfully saved to '{filepath}'")
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise

        return filepath

    #
    # ファイルの解析
    #
    def _parse_to_fileinfo(self, filepath: Path) -> Optional[FileInfo]:
        """ファイル名から FileInfo を抽出"""
        pattern = rf"{FILENAME_PATTERN}"
        mob = re.match(pattern, filepath.stem)

        if mob:
            try:
                nth = int(mob.group(1)) if mob.group(1) else None
                dosage = mob.group(2)
                medical_class = mob.group(3) or MEDICAL_CLASS_DEFAULT_VALUE
                method = mob.group(4)

                return FileInfo(
                    nth=nth,
                    dosage=dosage,
                    medical_class=medical_class,
                    method=method,
                    url=str(filepath)
                )
            except (IndexError, ValueError) as e:
                logger.warning(f'ファイル名の解析に失敗: {e}')
                return None

        return None

    #
    # フィルタリング
    #
    def _filter_files(
            self,
            fileinfos: Optional[List[FileInfo]] = None,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[str, List[str], None] = None,
            medical_class: Union[str, List[str], None] = None,
            method: Union[str, List[str], None] = None
    ) -> List[FileInfo]:
        """条件に合致するファイル情報をフィルタリング"""
        if fileinfos is None:
            files = self.fileinfo_list.copy()
        else:
            files = fileinfos.copy()
        available_nths = sorted(set(f.nth for f in files if f.nth is not None))

        def resolve_nth(n: int) -> int:
            if n < 0:
                return available_nths[n]
            else:
                return n

        # nth で絞り込み
        if nth is not None:
            if isinstance(nth, int):
                nth_list = [resolve_nth(nth)]
            else:
                nth_list = [resolve_nth(n) for n in nth]
            files = [f for f in files if f.nth in nth_list]

        # year で絞り込み（nth がない場合のみ）
        elif year is not None:
            year_list = [year] if isinstance(year, int) else year
            nth_list = [y - BASE_YEAR for y in year_list]
            files = [f for f in files if f.nth in nth_list]

        # dosage で絞り込み
        if dosage is not None:
            dosage_list = [dosage] if isinstance(dosage, str) else dosage
            files = [f for f in files if f.dosage in dosage_list]

        # medical_class で絞り込み
        if medical_class is not None:
            medical_class_list = [medical_class] if isinstance(medical_class, str) else medical_class
            files = [f for f in files if (f.medical_class in medical_class_list) or (f.medical_class == MEDICAL_CLASS_DEFAULT_VALUE)]

        # method で絞り込み
        if method is not None:
            method_list = [method] if isinstance(method, str) else method
            files = [f for f in files if f.method in method_list]

        return files

    #
    # データ読み込み（ヘルパー）
    #
    def _read_files(
            self,
            files: List[FileInfo],
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None],
            include_total: bool,
            progress_bar: bool,
            desc: str = 'Loading...'
    ) -> Optional[pd.DataFrame]:
        """ファイル情報を基にデータを読み込み・結合"""
        dfs = []
        for fileinfo in tqdm(files, desc=desc, disable=not progress_bar):
            try:
                df = self.transformer.read_file(
                    fileinfo,
                    condition_medical_class=medical_class,
                    include_total=include_total
                )
                dfs.append(df)
            except Exception as e:
                logger.error(f'ファイルの読み込みに失敗: {fileinfo.url} - {e}')

        if not dfs:
            return None

        return pd.concat(dfs, axis=0, ignore_index=True)

    #
    # データ読み込み（内部）
    #
    def _load(
            self,
            method: Literal['性年齢別', '都道府県別', '診療月別'],
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar: bool = True
    ) -> Optional[pd.DataFrame]:
        """厚労省HPから処方薬データをダウンロード・読み込み"""
        assert method in METHOD_VALUES, f"method は {METHOD_VALUES} のいずれかを指定してください"

        files = self._filter_files(
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            method=method
        )

        if len(files) == 0:
            logger.warning('条件に合致するファイルが見つかりません')
            return None

        return self._read_files(
            files,
            medical_class=medical_class,
            include_total=include_total,
            progress_bar=progress_bar
        )

    #
    # データ読み込み（性年齢別）
    #
    def load_age(
            self,
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar: bool = True
    ) -> Optional[pd.DataFrame]:
        """性年齢別の処方薬データを読み込み

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            '性年齢別',
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            include_total=include_total,
            progress_bar=progress_bar
        )

    #
    # データ読み込み（都道府県別）
    #
    def load_pref(
            self,
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar: bool = True
    ) -> Optional[pd.DataFrame]:
        """都道府県別の処方薬データを読み込み

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            '都道府県別',
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            include_total=include_total,
            progress_bar=progress_bar
        )

    #
    # データ読み込み（診療月別）
    #
    def load_month(
            self,
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            include_total: bool = False,
            progress_bar: bool = True
    ) -> Optional[pd.DataFrame]:
        """診療月別の処方薬データを読み込み

        ※【診療月別】は第10回（2023年度）以降のみ。歯科用薬剤は対象外。

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            '診療月別',
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            include_total=include_total,
            progress_bar=progress_bar
        )

    #
    # ファイル保存
    #
    def save(
            self,
            save_dir: Union[str, os.PathLike],
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            method: Union[Literal['性年齢別', '都道府県別', '診療月別'], List[Literal['性年齢別', '都道府県別', '診療月別']], None] = None,
            progress_bar: bool = True
    ) -> List[str]:
        """Excelファイルをダウンロードしてローカルに保存

        Args:
            save_dir: 保存先フォルダ。
            nth: 実施回。単一値または配列で指定可能。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            method: 集計方法。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            保存したファイルパス (str) のリスト
        """
        fileinfos = self._filter_files(
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            method=method
        )

        if not fileinfos:
            logger.warning('条件に合致するファイルが見つかりません')
            return []

        download_files = []
        for fileinfo in tqdm(fileinfos, desc='Downloading...', disable=not progress_bar):
            try:
                filepath = self._get_file(fileinfo, save_dir)
                download_files.append(str(filepath))
            except Exception as e:
                logger.error(f'ファイルのダウンロードに失敗: {fileinfo.url} - {e}')

        return download_files

    #
    # ローカルファイル読み込み
    #
    def read_excel(
            self,
            filepath: Union[str, os.PathLike],
            *,
            nth: Union[int, List[int], None] = None,
            year: Union[int, List[int], None] = None,
            dosage: Union[Literal['内服', '外用', '注射', '歯科用薬剤'], List[Literal['内服', '外用', '注射', '歯科用薬剤']], None] = None,
            medical_class: Union[Literal['外来（院内）', '外来（院外）', '入院'], List[Literal['外来（院内）', '外来（院外）', '入院']], None] = None,
            method: Union[Literal['性年齢別', '都道府県別', '診療月別'], List[Literal['性年齢別', '都道府県別', '診療月別']], None] = None,
            include_total: bool = False,
            progress_bar: bool = True
    ) -> Optional[pd.DataFrame]:
        """ローカルに保存されたExcelファイルを読み込み

        Args:
            filepath: 読み込み元のExcelファイルまたはディレクトリ。
                ファイルの場合：単一ファイルを読み込み。
                ディレクトリの場合：内部の.xlsxファイルをフィルタリングして読み込み。
                ファイル名は `"{nth}【{dosage}】{medical_class}_{method}薬効分類別数量.xlsx"` の形式が必須。
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            method: 集計方法。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        # パス型に統一
        if isinstance(filepath, str):
            filepath = Path(filepath)

        if not isinstance(filepath, Path):
            raise ValueError(f"Invalid filepath: '{filepath}'")

        if filepath.is_file():
            # 単一ファイルの場合
            if not filepath.parent.is_dir():
                raise FileNotFoundError(f"No such file: '{filepath}'")

            fileinfo = self._parse_to_fileinfo(filepath)
            if not fileinfo:
                raise ValueError(f"ファイル名が不正です。'{filepath.name}'")

            return self._read_files(
                [fileinfo],
                medical_class=medical_class,
                include_total=include_total,
                progress_bar=progress_bar,
                desc='Loading file...'
            )

        elif filepath.is_dir():
            # ディレクトリの場合：内部ファイルをフィルタリングして読み込み
            local_fileinfos = []
            for f in filepath.iterdir():
                if f.is_file() and f.suffix == '.xlsx':
                    fileinfo = self._parse_to_fileinfo(f)
                    if fileinfo:
                        local_fileinfos.append(fileinfo)

            if not local_fileinfos:
                logger.warning('ディレクトリに有効なファイルが見つかりません')
                return None

            files = self._filter_files(
                fileinfos=local_fileinfos,
                nth=nth,
                year=year,
                dosage=dosage,
                medical_class=medical_class,
                method=method
            )

            if len(files) == 0:
                logger.warning('条件に合致するファイルが見つかりません')
                return None

            return self._read_files(
                files,
                medical_class=medical_class,
                include_total=include_total,
                progress_bar=progress_bar,
                desc='Loading local files...'
            )

        else:
            raise FileNotFoundError(f"No such file or directory: '{filepath}'")

    #
    # ファイル情報の取得
    #
    def get_fileinfo_list(self) -> List[FileInfo]:
        """取得したファイル情報の一覧を返す"""
        return self.fileinfo_list.copy()

    def get_available_years(self) -> List[int]:
        """利用可能な年度を返す"""
        years = sorted(set(f.nth + BASE_YEAR for f in self.fileinfo_list))
        return years

    def get_available_dosages(self) -> List[str]:
        """利用可能な剤形を返す"""
        dosages = sorted(set(f.dosage for f in self.fileinfo_list))
        return dosages

    def get_available_methods(self) -> List[str]:
        """利用可能な集計方法を返す"""
        methods = sorted(set(f.method for f in self.fileinfo_list))
        return methods
