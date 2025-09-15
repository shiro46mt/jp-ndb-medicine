import pytest
from jp_ndb_medicine import NDBMedicine

index_cols = ['実施回', '年度', '剤形', '診療区分', '薬効分類', '薬効分類名称', '医薬品コード', '医薬品名', '単位', '薬価基準収載医薬品コード', '薬価', '後発品区分']
value_cols = ['処方数量', '最小集計単位未満']

@pytest.fixture
def ndbm():
    ndbm = NDBMedicine()
    return ndbm


def test_load_age(ndbm):
    df = ndbm.load_age(nth=1, dosage='外用', medical_class='入院')

    assert df.columns.to_list() == index_cols + ['性別', '年齢', '年齢区間'] + value_cols

    assert set(df['実施回'].unique()) == set([1])
    assert set(df['剤形'].unique()) == set(['外用'])
    assert set(df['診療区分'].unique()) == set(['入院'])
    assert set(df['性別'].unique()) == set(['男', '女'])


def test_load_age_total(ndbm):
    df = ndbm.load_age(nth=1, dosage='外用', medical_class='入院', include_total=True)

    assert set(df['性別'].unique()) == set(['総計', '男', '女'])


def test_load_pref(ndbm):
    df = ndbm.load_pref(nth=[1, 2], dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'])

    assert df.columns.to_list() == index_cols + ['都道府県コード', '都道府県名'] + value_cols

    assert set(df['実施回'].unique()) == set([1, 2])
    assert set(df['剤形'].unique()) == set(['内服', '注射'])
    assert set(df['診療区分'].unique()) == set(['外来（院内）', '外来（院外）'])
    assert df['都道府県コード'].nunique() == 47


def test_load_pref_total(ndbm):
    df = ndbm.load_pref(nth=[1, 2], dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'], include_total=True)

    assert df['都道府県コード'].nunique() == 48


def test_load_month(ndbm):
    df = ndbm.load_month(nth=10, dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'])

    assert df.columns.to_list() == index_cols + ['診療月', '診療年月'] + value_cols

    assert set(df['実施回'].unique()) == set([10])
    assert set(df['剤形'].unique()) == set(['内服', '注射'])
    assert set(df['診療区分'].unique()) == set(['外来（院内）', '外来（院外）'])
    assert df['診療月'].nunique() == 12
    assert df['診療年月'].nunique() == 12


def test_load_month_total(ndbm):
    df = ndbm.load_month(nth=10, dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'], include_total=True)

    assert df['診療月'].nunique() == 13
    assert df['診療年月'].nunique() == 13


def test_load_month_old(ndbm):
    df = ndbm.load_month(nth=list(range(1, 10)), dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'], include_total=True)

    assert df is None
