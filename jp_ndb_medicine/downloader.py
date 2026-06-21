import tempfile
import re
import zipfile
from pathlib import Path
from logging import Logger
from typing import List

import requests

from .constants import TIMEOUT_SEC, FILENAME_PATTERN
from .models import FileInfo


class NDBDownloader:
    """ファイルのダウンロードとZIP展開を担当するクラス"""

    def __init__(self, logger: Logger):
        self.logger = logger

    def download(self, fileinfo: FileInfo, save_dir: Path) -> Path:
        """URLからファイルをダウンロードして `save_dir` に保存し、保存先 Path を返す"""
        save_dir.mkdir(parents=True, exist_ok=True)
        filename = str(fileinfo)
        filepath = save_dir / filename

        try:
            self.logger.info(f"Downloading '{filename}' from '{fileinfo.url}'")
            r = requests.get(fileinfo.url, timeout=TIMEOUT_SEC)
            r.raise_for_status()
            with open(filepath, 'wb') as f:
                f.write(r.content)
            self.logger.info(f"Successfully saved to '{filepath}'")
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            raise

        return filepath

    def download_and_extract_zip(self, fileinfo: FileInfo, extract_to: Path) -> List[Path]:
        """ZIPファイルをダウンロードして展開。展開したファイルの Path リストを返す。"""
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            zip_path = self.download(fileinfo, td_path)

            extracted = []
            try:
                with zipfile.ZipFile(zip_path, 'r') as z:
                    # ZIP Slip対策
                    for info in z.infolist():
                        target = td_path / info.filename
                        if not target.resolve().is_relative_to(td_path.resolve()):
                            raise ValueError(f"Invalid zip entry: {info.filename}")

                    z.extractall(td_path)
                    for info in z.infolist():
                        if info.is_dir():
                            continue

                        pattern = rf"{FILENAME_PATTERN}\.xlsx"
                        mob = re.search(pattern, info.filename)
                        if mob:
                            if (mob.group(2) == '歯科用薬剤' and mob.group(5) == '_歯科') or mob.group(5) is None:
                                extracted.append(td_path / info.filename)

            except Exception as e:
                self.logger.error(f"ZIP extraction failed: {e}")
                raise

            # コピー先ディレクトリを作成してファイルを移動
            extract_to.mkdir(parents=True, exist_ok=True)
            final_paths: List[Path] = []
            for p in extracted:
                dest = extract_to / f'{fileinfo.nth:0>2}{p.name}'
                p.replace(dest)
                final_paths.append(dest)

        return final_paths
