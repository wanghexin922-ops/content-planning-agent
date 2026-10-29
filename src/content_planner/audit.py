"""Independent artifact auditor. Does not call the planner's calculation/tools.

The source request, material catalog, price catalog and database record are the
oracles; reported feasible flags and row totals are not accepted as evidence.
"""
from datetime import datetime, timedelta
from decimal import Decimal


def number(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a monetary value')
    result=Decimal(str(value))
    if not result.is_finite():
        raise ValueError('non-finite value')
    return result


def date(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone is required')
    return result


def audit_result(request, result, materials, pricing, clock, database_plan=None, previous=None):
    """Implementation with local validation closures."""
    checks={}
    catalog={m['id']:m for m in materials}
    def check(label, assertion):
        checks[label]=checks.get(label,True) and bool(assertion)

    def validate_script(script):
        ids=script['material_ids']
        check('valid_material_ids',bool(ids) and len(set(ids))==len(ids) and all(mid in catalog for mid in ids))
        check('theme_and_audience_preserved',script['theme']==request['theme'] and script['audience']==(request.get('audience') or '未指定受众（待运营确认）'))
        check('no_unverified_angle',script['angle'] in ('功能介绍','操作演示','场景引导'))
        check('creative_proposal_is_bounded',script['creative_direction']['text']==script['angle'] and script['creative_direction']['is_product_fact'] is False)
        check('original_topic_supported',all(any(t.lower() in request['theme'].lower() for t in catalog[mid]['topic_terms']) for mid in ids))
        facts=[s for s in script['scenes'] if s.get('kind')=='product_fact']
        check('product_claims_have_sources',bool(facts) and all(s['source_ids'] for s in facts))
        check('citations_support_claims',all(mid in ids and s['narration'] in catalog[mid]['facts'] for s in script['scenes'] for mid in s['source_ids']))

    def validate_estimate(e,script,must_be_feasible=False):
        cost_material=sum((number(catalog[mid]['cost']) for mid in script['material_ids']),Decimal(0))
        mode=pricing['production_modes'][e['production_mode']]
        expected=[('materials',cost_material,0),('script',number(pricing['script']['cost']),pricing['script']['minutes']),
                  ('production',number(mode['cost']),mode['minutes']),('review',number(pricing['review']['cost']),pricing['review']['minutes']),
                  ('publish',number(pricing['publish']['cost']),pricing['publish']['minutes'])]
        total=sum((r[1] for r in expected),Decimal(0))
        minutes=sum(r[2] for r in expected)
        finish=date(clock)+timedelta(minutes=minutes)
        feasible=total<=number(request['budget']) and finish<=date(request['deadline'])
        check('cost_recomputed_from_source',number(e['total_cost'])==total)
        check('time_recomputed_from_source',e['total_minutes']==minutes and date(e['estimated_finish'])==finish)
        check('constraints_preserved',number(e['budget'])==number(request['budget']) and date(e['deadline'])==date(request['deadline']))
        check('feasibility_independently_verified',e['feasible'] is feasible)
        check('gaps_independently_verified',number(e['budget_gap'])==max(Decimal(0),total-number(request['budget'])) and abs(e['deadline_gap_minutes']-max(0,(finish-date(request['deadline'])).total_seconds()/60))<0.001)
        check('mandatory_stages_present',[s['id'] for s in e['steps']]==[r[0] for r in expected])
        cursor=date(clock)
        for index,(sid,cost,duration) in enumerate(expected):
            row=e['steps'][index]
            end=cursor+timedelta(minutes=duration)
            check('stage_costs_and_durations',row['id']==sid and number(row['cost'])==cost and row['duration_minutes']==duration)
            check('dependency_and_schedule_valid',row['depends_on']==([] if index==0 else [expected[index-1][0]]) and date(row['start'])==cursor and date(row['end'])==end and row['status']=='planned')
            cursor=end
        if must_be_feasible:
            check('saved_plan_satisfies_constraints',feasible)

    try:
        steps=result['steps']
        check('step_status_matches_result',all((s['status']=='succeeded') is (s['result']['ok'] is True) for s in steps))
        check('tool_counter_matches_records',result['tool_calls']==len(steps))
        scripts={}
        retrieved=set()
        for s in steps:
            if s['result']['ok'] and s['tool']=='search_materials':
                for m in s['result']['materials']:
                    check('retrieval_matches_source',catalog.get(m['id'])==m)
                    retrieved.add(m['id'])
            if s['result']['ok'] and s['tool']=='generate_script':
                script=s['result']['script']
                check('script_uses_observed_materials',set(script['material_ids'])<=retrieved)
                validate_script(script)
                scripts[s['result']['script_id']]=script
            if s['result']['ok'] and s['tool']=='estimate_plan':
                e=s['result']['estimate']
                check('estimate_has_successful_script',e['script_id'] in scripts)
                validate_estimate(e,scripts[e['script_id']])
        check('successful_artifacts_preserved',scripts==result['successful_artifacts']['scripts'])
        check('saved_state_matches_database',bool(database_plan)==result['saved'])
        if database_plan:
            plan=result['plan']
            check('database_plan_matches_output',database_plan['plan']==plan and database_plan['plan_id']==result['plan_id'])
            check('request_identity_preserved',plan['request_id']==request['request_id'] and plan['theme']==request['theme'] and plan['audience']==request.get('audience','未指定'))
            check('business_not_executed',plan['execution_status']=='not_executed')
            check('saved_script_is_successful_artifact',scripts.get(plan['estimate']['script_id'])==plan['script'])
            validate_script(plan['script'])
            validate_estimate(plan['estimate'],plan['script'],must_be_feasible=True)
            check('output_total_matches_plan',number(result['total_cost'])==number(plan['estimate']['total_cost']))
        else:
            check('no_false_completion',result['status']!='completed' and result['plan'] is None and result['plan_id'] is None)
        if previous:
            check('repeat_preserves_tool_history',result['steps']==previous['steps'] and result['model_calls']==previous['model_calls'])
            check('repeat_preserves_plan',result['plan_id']==previous['plan_id'] and result['plan']==previous['plan'])
    except (KeyError,TypeError,ValueError,ArithmeticError,IndexError,AttributeError):
        checks['well_formed_artifacts']=False
    return checks

