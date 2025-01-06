import pytest
from jp_ndb_medicine import NDBMedicine

index_cols = ['実施回', '年度', '剤形', '診療区分', '薬効分類', '薬効分類名称', '医薬品コード', '医薬品名', '単位', '薬価基準収載医薬品コード', '薬価', '後発品区分']

@pytest.fixture
def ndbm():
    ndbm = NDBMedicine()
    return ndbm


def test_load_age(ndbm):
    df = ndbm.load_age(nth=1, dosage='外用', medical_class='入院')

    assert df.columns.to_list() == index_cols + ['性別', '年齢', '年齢区間', '量']

    assert set(df['実施回'].unique()) == set([1])
    assert set(df['剤形'].unique()) == set(['外用'])
    assert set(df['診療区分'].unique()) == set(['入院'])


def test_load_pref(ndbm):
    df = ndbm.load_pref(nth=[1, 2], dosage=['内服', '注射'], medical_class=['外来（院内）', '外来（院外）'])

    assert df.columns.to_list() == index_cols + ['都道府県コード', '都道府県名', '量']

    assert set(df['実施回'].unique()) == set([1, 2])
    assert set(df['剤形'].unique()) == set(['内服', '注射'])
    assert set(df['診療区分'].unique()) == set(['外来（院内）', '外来（院外）'])
