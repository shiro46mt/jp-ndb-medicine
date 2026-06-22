import re

# URL設定
DOMAIN_MHLW = "https://www.mhlw.go.jp"
URL_TOP = "https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177182.html"
HEADERS = {"User-Agent": ""}

# データ設定
BASE_YEAR = 2013
TIMEOUT_SEC = 60
INTERVAL_SEC = 0.1

# 値の定義
DOSAGE_VALUES = ("内服", "外用", "注射", "歯科用薬剤")
MEDICAL_CLASS_VALUES = ("外来（院内）", "外来（院外）", "入院")
METHOD_VALUES = ("性年齢別", "都道府県別", "診療月別")
INDEX_COLS = [
    "薬効分類",
    "薬効分類名称",
    "医薬品コード",
    "医薬品名",
    "単位",
    "薬価基準収載医薬品コード",
    "薬価",
    "後発品区分",
]

# 正規表現パターン
NTH_PATTERN = re.compile(r"第(\d+)回NDBオープンデータ")
DOSAGE_PATTERN = "|".join(DOSAGE_VALUES)
MEDICAL_CLASS_PATTERN = "|".join(MEDICAL_CLASS_VALUES)
METHOD_PATTERN = "|".join(METHOD_VALUES)
FILENAME_PATTERN = (
    rf"(\d\d)?【({DOSAGE_PATTERN})】({MEDICAL_CLASS_PATTERN})?_?({METHOD_PATTERN})薬効分類別数量(_歯科)?(\(公費含む\))?"
)
