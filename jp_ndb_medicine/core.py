import os
import shutil
import tempfile
from logging import getLogger
from pathlib import Path
from typing import Literal, Optional, Union

import pandas as pd
from tqdm import tqdm

from .constants import BASE_YEAR, DOSAGE_VALUES, METHOD_VALUES
from .downloader import NDBDownloader
from .helpers import _parse_to_fileinfo
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
        self.downloader = NDBDownloader(logger)
        self.fileinfo_list: list[FileInfo] = []

        try:
            self.fileinfo_list = self.scraper.fetch_all()
            logger.info(f"ファイル情報を取得しました: {len(self.fileinfo_list)}件")
        except Exception as e:
            logger.warning(f"NDBオープンデータのページにアクセスできません: {e}")

    #
    # フィルタリング
    #
    def _filter_files(
        self,
        *,
        fileinfos: Optional[list[FileInfo]] = None,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[str, list[str], None] = None,
        medical_class: Union[str, list[str], None] = None,
        method: Union[str, list[str], None] = None,
        public_fund: bool = True,
    ) -> list[FileInfo]:
        """条件に合致するファイル情報をフィルタリング"""
        if fileinfos is None:
            files = self.fileinfo_list
        else:
            files = fileinfos

        # nth, year 引数の解析
        nth_list = None
        available_nths = self.get_available_nth()

        def resolve_nth(n: int) -> int:
            if n < 0:
                return available_nths[n]
            else:
                return n

        if nth is not None:
            if isinstance(nth, int):
                nth_list = [resolve_nth(nth)]
            else:
                nth_list = [resolve_nth(n) for n in nth]

        elif year is not None:
            if isinstance(year, int):
                nth_list = [year - BASE_YEAR]
            else:
                nth_list = [y - BASE_YEAR for y in year]

        # 条件に合致するファイル情報を返す
        return [
            f
            for f in files
            if f.match(
                nth=nth_list,
                dosage=dosage,
                medical_class=medical_class,
                method=method,
                public_fund=public_fund,
            )
        ]

    #
    # データ読み込み（ヘルパー）
    #
    def _read_files(
        self,
        files: list[FileInfo],
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ],
        include_total: bool,
        progress_bar: bool,
        desc: str = "Loading...",
    ) -> Optional[pd.DataFrame]:
        """ファイル情報を基にデータを読み込み・結合"""
        dfs = []
        for fileinfo in tqdm(files, desc=desc, disable=not progress_bar):
            try:
                df = self.transformer.read_file(
                    fileinfo,
                    condition_medical_class=medical_class,
                    include_total=include_total,
                )
                dfs.append(df)
            except Exception as e:
                logger.error(f"ファイルの読み込みに失敗: {fileinfo.url} - {e}")

        if not dfs:
            return None

        return pd.concat(dfs, axis=0, ignore_index=True)

    #
    # データ読み込み（内部）
    #
    def _load(
        self,
        method: Literal["性年齢別", "都道府県別", "診療月別"],
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        public_fund: bool = True,
        include_total: bool = False,
        progress_bar: bool = True,
    ) -> Optional[pd.DataFrame]:
        """厚労省HPから処方薬データをダウンロード・読み込み"""
        assert method in METHOD_VALUES, f"method は {METHOD_VALUES} のいずれかを指定してください"

        files = self._filter_files(
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            method=method,
            public_fund=public_fund,
        )

        if len(files) == 0:
            logger.warning("条件に合致するファイルが見つかりません")
            return None

        # ZIP ファイルが含まれる場合はダウンロードして展開し、内部の xlsx をフィルタリングして追加する
        zip_files = [f for f in files if f.is_zip_file]
        xlsx_files = [f for f in files if not f.is_zip_file]
        temp_extract_dir = None
        if zip_files:
            temp_extract_dir = Path(tempfile.mkdtemp(prefix="jp_ndb_medicine_"))
            extracted_fileinfos: list[FileInfo] = []
            for z in zip_files:
                try:
                    extracted_paths = self.downloader.download_and_extract_zip(z, temp_extract_dir)
                    for p in extracted_paths:
                        fi = _parse_to_fileinfo(p, logger)
                        if fi:
                            extracted_fileinfos.append(fi)
                except Exception as e:
                    logger.error(f"ZIP のダウンロード/展開に失敗: {z.url} - {e}")

            if extracted_fileinfos:
                matched = self._filter_files(
                    fileinfos=extracted_fileinfos,
                    nth=nth,
                    year=year,
                    dosage=dosage,
                    medical_class=medical_class,
                    method=method,
                    public_fund=public_fund,
                )
                # 展開された一致ファイルを読み込み対象に追加
                xlsx_files.extend(matched)

        try:
            return self._read_files(
                xlsx_files,
                medical_class=medical_class,
                include_total=include_total,
                progress_bar=progress_bar,
            )
        finally:
            if temp_extract_dir is not None:
                try:
                    shutil.rmtree(temp_extract_dir)
                except Exception:
                    pass

    #
    # データ読み込み（性年齢別）
    #
    def load_age(
        self,
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        public_fund: bool = True,
        include_total: bool = False,
        progress_bar: bool = True,
    ) -> Optional[pd.DataFrame]:
        """性年齢別の処方薬データを読み込み

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            public_fund: `True`の場合、公費レセプトを含むデータを読み込む（第10回以降）。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            "性年齢別",
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            public_fund=public_fund,
            include_total=include_total,
            progress_bar=progress_bar,
        )

    #
    # データ読み込み（都道府県別）
    #
    def load_pref(
        self,
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        public_fund: bool = True,
        include_total: bool = False,
        progress_bar: bool = True,
    ) -> Optional[pd.DataFrame]:
        """都道府県別の処方薬データを読み込み

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            public_fund: `True`の場合、公費レセプトを含むデータを読み込む（第10回以降）。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            "都道府県別",
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            public_fund=public_fund,
            include_total=include_total,
            progress_bar=progress_bar,
        )

    #
    # データ読み込み（診療月別）
    #
    def load_month(
        self,
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        public_fund: bool = True,
        include_total: bool = False,
        progress_bar: bool = True,
    ) -> Optional[pd.DataFrame]:
        """診療月別の処方薬データを読み込み

        ※【診療月別】は第10回（2023年度）以降のみ。歯科用薬剤は対象外。

        Args:
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            public_fund: `True`の場合、公費レセプトを含むデータを読み込む（第10回以降）。
            include_total: `True`の場合、総計行を含める。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            `pd.DataFrame` または `None`（該当データなし）
        """
        return self._load(
            "診療月別",
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            public_fund=public_fund,
            include_total=include_total,
            progress_bar=progress_bar,
        )

    #
    # ファイル保存
    #
    def save(
        self,
        save_dir: Union[str, os.PathLike],
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        method: Union[
            Literal["性年齢別", "都道府県別", "診療月別"],
            list[Literal["性年齢別", "都道府県別", "診療月別"]],
            None,
        ] = None,
        public_fund: bool = True,
        progress_bar: bool = True,
    ) -> list[str]:
        """Excelファイルをダウンロードしてローカルに保存

        Args:
            save_dir: 保存先フォルダ。
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            method: 集計方法。
            public_fund: `True`の場合、公費レセプトを含むデータを読み込む（第10回以降）。
            progress_bar: `True`の場合、進捗バーを表示。

        Returns:
            保存したファイルパス (str) のリスト
        """
        if isinstance(save_dir, str):
            save_dir = Path(save_dir)

        if not isinstance(save_dir, Path) or not save_dir.is_dir():
            raise FileNotFoundError(f"No such directory: '{save_dir}'")

        fileinfos = self._filter_files(
            nth=nth,
            year=year,
            dosage=dosage,
            medical_class=medical_class,
            public_fund=public_fund,
            method=method,
        )

        if not fileinfos:
            logger.warning("条件に合致するファイルが見つかりません")
            return []

        download_files = []
        for fileinfo in tqdm(fileinfos, desc="Downloading...", disable=not progress_bar):
            try:
                filepath = self.downloader.download(fileinfo, save_dir)
                if filepath not in download_files:
                    download_files.append(str(filepath))
            except Exception as e:
                logger.error(f"ファイルのダウンロードに失敗: {fileinfo.url} - {e}")

        return download_files

    #
    # ローカルファイル読み込み
    #
    def read_excel(
        self,
        filepath: Union[str, os.PathLike],
        *,
        nth: Union[int, list[int], None] = None,
        year: Union[int, list[int], None] = None,
        dosage: Union[
            Literal["内服", "外用", "注射", "歯科用薬剤"],
            list[Literal["内服", "外用", "注射", "歯科用薬剤"]],
            None,
        ] = None,
        medical_class: Union[
            Literal["外来（院内）", "外来（院外）", "入院"],
            list[Literal["外来（院内）", "外来（院外）", "入院"]],
            None,
        ] = None,
        method: Union[
            Literal["性年齢別", "都道府県別", "診療月別"],
            list[Literal["性年齢別", "都道府県別", "診療月別"]],
            None,
        ] = None,
        public_fund: bool = True,
        include_total: bool = False,
        progress_bar: bool = True,
    ) -> Optional[pd.DataFrame]:
        """ローカルに保存されたExcelファイルを読み込み

        Args:
            filepath: 読み込み元のExcelファイルまたはディレクトリ。
                ファイルの場合：単一ファイルを読み込み。
                ディレクトリの場合：内部の.xlsxファイルをフィルタリングして読み込み。
                ファイル名は `"{nth}【{dosage}】{medical_class}_{method}薬効分類別数量.xlsx"` または `"{nth}【{dosage}】{medical_class}_{method}薬効分類別数量(公費含む).xlsx"` の形式が必須。
            nth: 実施回。単一値または配列で指定可能。負の値を指定すると、利用可能な実施回のリストから後ろから数える（-1は最新、-2は最新の1つ前、など）。
            year: 実施年度。`nth` とともに指定した場合、`nth` が優先される。
            dosage: 剤形。
            medical_class: 診療区分。
            method: 集計方法。
            public_fund: `True`の場合、公費レセプトを含むデータを読み込む（第10回以降）。
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
            fileinfo = _parse_to_fileinfo(filepath, logger)
            if not fileinfo:
                raise ValueError(f"ファイル名が不正です。'{filepath.name}'")

            return self._read_files(
                [fileinfo],
                medical_class=medical_class,
                include_total=include_total,
                progress_bar=progress_bar,
                desc="Loading file...",
            )

        elif filepath.is_dir():
            # ディレクトリの場合：内部ファイルを再帰的にフィルタリングして読み込み
            local_fileinfos = []
            for f in filepath.rglob("*.xlsx"):
                if f.is_file():
                    fileinfo = _parse_to_fileinfo(f, logger)
                    if fileinfo:
                        local_fileinfos.append(fileinfo)

            if not local_fileinfos:
                logger.warning("ディレクトリに有効なファイルが見つかりません")
                return None

            files = self._filter_files(
                fileinfos=local_fileinfos,
                nth=nth,
                year=year,
                dosage=dosage,
                medical_class=medical_class,
                method=method,
                public_fund=public_fund,
            )

            if len(files) == 0:
                logger.warning("条件に合致するファイルが見つかりません")
                return None

            return self._read_files(
                files,
                medical_class=medical_class,
                include_total=include_total,
                progress_bar=progress_bar,
                desc="Loading local files...",
            )

        else:
            raise FileNotFoundError(f"No such file or directory: '{filepath}'")

    #
    # ファイル情報の取得
    #
    def get_fileinfo_list(self) -> list[FileInfo]:
        """取得したファイル情報の一覧を返す"""
        return self.fileinfo_list.copy()

    def get_available_nth(self) -> list[int]:
        """利用可能な実施回を返す"""
        nths = sorted({f.nth for f in self.fileinfo_list})
        return nths

    def get_available_years(self) -> list[int]:
        """利用可能な年度を返す"""
        years = sorted({f.year for f in self.fileinfo_list})
        return years

    def get_available_dosages(self, *, nth: Optional[int] = None) -> list[str]:
        """利用可能な剤形を返す"""
        if nth and nth < 7:
            return ("内服", "外用", "注射")
        else:
            return DOSAGE_VALUES

    def get_available_methods(self, *, nth: Optional[int] = None) -> list[str]:
        """利用可能な集計方法を返す"""
        if nth and nth < 10:
            return ("性年齢別", "都道府県別")
        else:
            return METHOD_VALUES
