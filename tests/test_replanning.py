import sys
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from evaluate import CASES, NOW, request_for, case_data, check_result
from content_planner.agent import run_agent
from content_planner.model import MockModel
from content_planner.storage import Store
from content_planner.common import read_json, timestamp

ROOT=Path(__file__).resolve().parents[1]


class ReplanningTests(unittest.TestCase):
    def run_case(self,name):
        data=read_json(ROOT/'data/materials.json')
        pricing=read_json(ROOT/'data/pricing.json')
        spec=CASES[name]
        selected,prices=case_data(data,pricing,spec)
        self.assertEqual(pricing['production_modes']['basic']['cost'],3)
        req=request_for(name,spec)
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(Path(tmp)/'state.sqlite')
            try:
                result=run_agent(req,MockModel(req),store,selected,prices,now=lambda:timestamp(NOW),faults=spec.get('faults'))
            finally:
                store.close()
        self.assertTrue(all(check_result(name,spec,result).values()))
        return result

    def test_tight_time_selects_faster_feasible_plan(self):
        result=self.run_case('time_pressure')
        self.assertLessEqual(result['plan']['estimate']['total_minutes'],100)

    def test_changed_prices_are_used(self):
        result=self.run_case('price_changed')
        self.assertLessEqual(result['total_cost'],7)
        first=next(s['result']['estimate'] for s in result['steps'] if s['tool']=='estimate_plan')
        self.assertEqual(first['total_cost'],14)

    def test_materials_can_be_replaced_to_fit_budget(self):
        result=self.run_case('material_switch')
        self.assertEqual(result['plan']['script']['material_ids'],['P02'])
        self.assertEqual(result['total_cost'],4)

    def test_persistent_failure_stops_without_losing_search(self):
        result=self.run_case('persistent_failure')
        self.assertTrue(result['successful_artifacts']['retrieved_ids'])
        self.assertFalse(result['saved'])
