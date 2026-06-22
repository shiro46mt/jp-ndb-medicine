from typing import NamedTuple, Optional, Union

from .constants import BASE_YEAR


class FileInfo(NamedTuple):
    url: str
    nth: int
    public_fund: bool
    dosage: Optional[str] = None
    medical_class: Optional[str] = None
    method: Optional[str] = None
    is_zip_file: bool = False

    def __str__(self):
        if self.is_zip_file:
            public_fund_str = "公費レセプトを含むデータ" if self.public_fund else "公費レセプトを含まないデータ"
            return f"{self.nth:0>2d}_{public_fund_str}.zip"
        else:
            public_fund_str = "(公費含む)" if self.public_fund else ""
            return f"{self.nth:0>2d}【{self.dosage}】{self.medical_class}_{self.method}薬効分類別数量{public_fund_str}.xlsx"

    @property
    def year(self) -> int:
        """年を返す（nth から計算）"""
        return BASE_YEAR + self.nth

    def match(
        self,
        nth: Union[int, list[int], None] = None,
        dosage: Union[str, list[str], None] = None,
        medical_class: Union[str, list[str], None] = None,
        method: Union[str, list[str], None] = None,
        public_fund: bool = True,
    ) -> bool:
        """条件に合致するかどうかを判定する"""
        # nth で絞り込み
        if nth is not None:
            if isinstance(nth, int):
                if self.nth != nth:
                    return False
            else:
                if self.nth not in nth:
                    return False

        # dosage で絞り込み
        if (dosage is not None) and (self.dosage is not None) and (self.dosage != ""):
            if isinstance(dosage, str):
                if self.dosage != dosage:
                    return False
            else:
                if self.dosage not in dosage:
                    return False

        # medical_class で絞り込み
        if (medical_class is not None) and (self.medical_class is not None) and (self.medical_class != ""):
            if isinstance(medical_class, str):
                if self.medical_class != medical_class:
                    return False
            else:
                if self.medical_class not in medical_class:
                    return False

        # method で絞り込み
        if (method is not None) and (self.method is not None) and (self.method != ""):
            if isinstance(method, str):
                if self.method != method:
                    return False
            else:
                if self.method not in method:
                    return False

        # public_fund で絞り込み（第10回以降）
        if self.nth >= 10:
            if self.public_fund != public_fund:
                return False

        return True
