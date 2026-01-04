[![pytest](https://github.com/shiro46mt/jp-ndb-medicine/actions/workflows/pytest.yml/badge.svg)](https://github.com/shiro46mt/jp-ndb-medicine/actions/workflows/pytest.yml)
![GitHub License](https://img.shields.io/github/license/shiro46mt/jp-ndb-medicine)
[![PyPI - Version](https://img.shields.io/pypi/v/jp-ndb-medicine)](https://pypi.org/project/jp-ndb-medicine/)
[![PyPI Downloads](https://static.pepy.tech/badge/jp-ndb-medicine)](https://pepy.tech/projects/jp-ndb-medicine)

# jp-ndb-medicine
NDBオープンデータから、処方薬のデータを簡単に取得・利用するためのpythonライブラリ

NDBオープンデータについての詳細は[厚生労働省HP](https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177182.html)を参照。

# インストール方法
```
pip install jp-ndb-medicine
```

# 使用例
```python
from jp_ndb_medicine import NDBMedicine
ndbm = NDBMedicine()
```

## Excelファイルを縦持ち形式で読み込む

性年齢別の例を示します。
都道府県別のデータを読み込みたい場合は `ndbm.load_pref()` を使用してください。

**抽出条件で指定できる値**
* `dosage`: 内服 / 外用 / 注射 / 歯科用薬剤
* `medical_class_values`: 外来（院内） / 外来（院外） / 入院

```python
df = ndbm.load_age()                            # 利用可能なすべてのデータ
df = ndbm.load_age(nth=[1, 2])                  # 第1,2回
df = ndbm.load_age(year=2014)                   # 2014年度
df = ndbm.load_age(dosage=['内服', '外用'])     # 内服または外用
df = ndbm.load_age(medical_class='入院')        # 入院分
df = ndbm.load_age(nth=1, dosage=['内服', '外用'], medical_class='入院')  # 条件の組み合わせ（AND検索）
```

**読み込み例：性年齢別**

※単位は第3回以降で利用可能。

実施回|年度|剤形|診療区分|薬効分類|薬効分類名称|医薬品コード|医薬品名|単位|薬価基準収載医薬品コード|薬価|後発品区分|性別|年齢|年齢区間|処方数量|最小集計単位未満
--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--
1|2014|内服|外来（院内）|112|催眠鎮静剤，抗不安剤|611170508|ソラナックス０．４ｍｇ錠||1124023F1037|9.2|0|男性|10|10～14歳|4757.2|0
1|2014|内服|外来（院内）|112|催眠鎮静剤，抗不安剤|611170508|ソラナックス０．４ｍｇ錠||1124023F1037|9.2|0|男性|15|15～19歳|46466|0

**読み込み例：都道府県別**

実施回|年度|剤形|診療区分|薬効分類|薬効分類名称|医薬品コード|医薬品名|単位|薬価基準収載医薬品コード|薬価|後発品区分|都道府県コード|都道府県名|処方数量|最小集計単位未満
--|--|--|--|--|--|--|--|--|--|--|--|--|--|--|--
1|2014|内服|外来（院内）|112|催眠鎮静剤，抗不安剤|611170508|ソラナックス０．４ｍｇ錠||1124023F1037|9.2|0|01|北海道|2411514|0
1|2014|内服|外来（院内）|112|催眠鎮静剤，抗不安剤|611170508|ソラナックス０．４ｍｇ錠||1124023F1037|9.2|0|02|青森県|746303.5|0

**総計の扱い**

`include_total=True` を指定した場合、成分ごとの総計行を含めて出力します。(version>=1.1)
総計行は元データの総計の列の値を使用しています。元データの総計には最小集計単位未満の値も含まれるため、明細の単純合計と一致しない場合があります。

> [!TIP]
>
> 全年齢または全都道府県の総計のみを使用したい場合は、総計行を使用するとより正確です。
>
> 年代別や地域別などの小計も使用したい場合は、総計行を使用すると小計とのずれが発生する可能性があることに留意してください。

本ライブラリでは、総計行では便宜上 `年齢`=-1（性年齢別の場合）、`都道府県コード`='00'（都道府県別の場合）としています。

**最小集計単位の扱い**

処方数量の集計結果が最小集計単位未満の場合、その集計結果はマスキングされます。
最小集計単位は、内服または外用の場合は1000、注射の場合は400（第2回までは1000）です。詳細は各回の解説編を参照。

本ライブラリでは、読み込みの際にマスキングされた処方数量を0に置き換えています。0に置き換えられた行には最小集計単位未満=1としてフラグをたてているので、実際に0の場合と区別可能です。(version>=1.1)

## Excelファイルをローカルに保存する

抽出条件は読み込む場合を参照。

```python
save_dir = '/path/to/directory'
filepaths = ndbm.save(save_dir)                     # 利用可能なすべてのデータ
filepaths = ndbm.save(save_dir, method='性年齢別')   # 性年齢別のみ
print(filepaths)  # ['/path/to/directory/01_内服_外来（院内）_性年齢別.xlsx', ...]
```

## ローカルに保存したExcelファイルを縦持ち形式で読み込む
```python
filepath = '/path/to/directory/01_内服_外来（院内）_性年齢別.xlsx'
df = ndbm.read_excel(filepath)
```

# License
This software is released under the MIT License, see LICENSE.

出典：「NDBオープンデータ」（厚生労働省） https://www.mhlw.go.jp/stf/seisakunitsuite/bunya/0000177182.html
