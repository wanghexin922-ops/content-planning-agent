import copy
from pathlib import Path
import tempfile
import unittest
from content_planner.audit import audit_result
from content_planner.agent import run_agent
from content_planner.model import MockModel
from content_planner.storage import Store
from content_planner.common import read_json, timestamp

ROOT=Path(__file__).resolve().parents[1]
NOW='2026-10-28T10:00:00+08:00'


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.req={'request_id':'audit-test','theme':'视频字幕工具','audience':'创作者','budget':15,'deadline':'2026-10-29T18:00:00+08:00'}
        cls.materials=read_json(ROOT/'data/materials.json')
        cls.pricing=read_json(ROOT/'data/pricing.json')
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state.sqlite')
            try:
                cls.original=run_agent(cls.req,MockModel(cls.req),store,cls.materials,cls.pricing,now=lambda:timestamp(NOW))
            finally:
                store.close()

    def setUp(self):
        self.out=copy.deepcopy(self.original)

    def audit(self):
        # Deliberately give the auditor a matching tampered DB record. The raw
        # source catalog and request must still catch self-consistent forgeries.
        db={'plan_id':self.out['plan_id'],'plan':copy.deepcopy(self.out['plan'])}
        return audit_result(self.req,self.out,self.materials,self.pricing,NOW,db)

    def test_valid_plan_passes(self):
        checks=self.audit()
        self.assertTrue(all(checks.values()),checks)

    def test_self_consistent_fake_price_fails(self):
        e=self.out['plan']['estimate']
        e['total_cost']=0
        self.out['total_cost']=0
        for row in e['steps']:
            row['cost']=0
        self.assertFalse(self.audit()['cost_recomputed_from_source'])

    def test_fake_time_and_feasibility_fail(self):
        e=self.out['plan']['estimate']
        e['total_minutes']=0
        e['estimated_finish']=NOW
        self.assertFalse(self.audit()['time_recomputed_from_source'])

    def test_omitted_review_fails(self):
        self.out['plan']['estimate']['steps'].pop(3)
        self.assertFalse(self.audit()['mandatory_stages_present'])

    def test_broken_dependencies_fail(self):
        self.out['plan']['estimate']['steps'][2]['depends_on']=[]
        self.assertFalse(self.audit()['dependency_and_schedule_valid'])

    def test_unsupported_fact_fails(self):
        scene=next(s for s in self.out['plan']['script']['scenes'] if s.get('kind')=='product_fact')
        scene['narration']='效率提升80%'
        self.assertFalse(self.audit()['citations_support_claims'])

    def test_false_source_id_fails(self):
        scene=next(s for s in self.out['plan']['script']['scenes'] if s.get('kind')=='product_fact')
        scene['source_ids']=['P03']
        self.assertFalse(self.audit()['citations_support_claims'])

    def test_changed_user_budget_fails(self):
        self.out['plan']['estimate']['budget']=999
        self.assertFalse(self.audit()['constraints_preserved'])

    def test_changed_theme_fails(self):
        self.out['plan']['theme']='别的主题'
        self.assertFalse(self.audit()['request_identity_preserved'])

    def test_failed_step_labelled_success_fails(self):
        self.out['steps'][0]['result']={'ok':False,'error':{'code':'fake'}}
        self.assertFalse(self.audit()['step_status_matches_result'])

    def test_lost_successful_artifact_fails(self):
        self.out['successful_artifacts']['scripts']={}
        self.assertFalse(self.audit()['successful_artifacts_preserved'])

    def test_claimed_save_without_database_fails(self):
        checks=audit_result(self.req,self.out,self.materials,self.pricing,NOW,None)
        self.assertFalse(checks['saved_state_matches_database'])

    def test_fake_feasibility_flag_fails(self):
        self.out['plan']['estimate']['feasible']=False
        self.assertFalse(self.audit()['feasibility_independently_verified'])
