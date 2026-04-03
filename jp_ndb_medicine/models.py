from typing import NamedTuple

class FileInfo(NamedTuple):
    nth: int
    dosage: str
    medical_class: str
    method: str
    url: str

    def __str__(self):
        return f"{self.nth:0>2d}【{self.dosage}】{self.medical_class}_{self.method}薬効分類別数量"
