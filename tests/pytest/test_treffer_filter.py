
import os,sys
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src import versand_service as vs

KAT = {"foerderungen": [{"id": "a", "status": "offen"}, {"id": "b", "status": "fenster_zu"},
                        {"id": "c", "status": "ausgeschoepft"}, {"id": "d", "status": "angekuendigt"}]}

def test_geschlossene_treffer_werden_entfernt():
    t = [{"foerderung_id": i} for i in "abcdx"]
    assert [x["foerderung_id"] for x in vs.offene_treffer_filtern(t, KAT)] == ["a", "d", "x"]
