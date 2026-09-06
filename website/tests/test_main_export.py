import importlib.util
import json
import hashlib
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('export_results', Path(__file__).parents[1] / 'scripts/export_results.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

def cohort():
    return {'id':'formal-47','case_count':3,'instances':['a::seed-1','b::seed-1','c::seed-1'],
            'themes':{'a::seed-1':'one','b::seed-1':'two','c::seed-1':'two'},
            'theme_counts':{'one':1,'two':2},'repetitions':3,'execution_modes':['linear','async'],
            'evaluation_contract_version':'11.0.0','evaluation_contract_sha256':'contract',
            'models':['model'],'seed':2026,'guidance':'incentive','selection_sha256':'a'*64}

def scores():
    return {(key,mode,rep): {'score_status':'scored','base_task_score':0 if key.startswith('a:') else 1,
            'async_drs':0 if key.startswith('a:') else 1,'split':'calibration' if key.startswith('a:') else 'test',
            'api_key':'DO-NOT-EXPORT','private_trace':{'secret':True}}
            for key in cohort()['instances'] for mode in ['linear','async'] for rep in range(3)}

def bound_manifest(episodes):
    return {'model':'model','episodes':episodes,'repetitions':3,'seed':2026,'guidance':'incentive',
            'evaluation_contract_version':'11.0.0','evaluation_contract_sha256':'contract',
            'case_bundle_sha256':{e['case_id']+'::'+e['instance_id']:'case' for e in episodes},
            'verifier_bundle_sha256':{e['case_id']+'::'+e['instance_id']:'verifier' for e in episodes}}

def bound_score(episode, digest):
    from async_rbench.evaluation.weighting import SCORE_POLICY_VERSION
    return {**episode,'manifest_sha256':digest,'score_status':'scored','base_task_score':0,'async_drs':0,
            'evaluation_contract_version':'11.0.0','evaluation_contract_sha256':'contract',
            'case_sha256':'case','verifier_bundle_sha256':'verifier','score_policy_version':SCORE_POLICY_VERSION,
            'conformance_passed':True,'protocol_valid':True,'runtime_mode':'api_only',
            'resource_policy_sha256':'resource','scaffold_and_protocol_sha256':'scaffold','child_pool_id':'pool',
            'leaderboard_eligible':False,'leaderboard_ineligibility_reasons':['split_not_test']}

class MainExportTests(unittest.TestCase):
    def test_committed_snapshot_uses_the_canonical_main_cohort(self):
        root=Path(__file__).resolve().parents[2]
        canonical=exporter.load_main_cohort(root)
        data=json.loads((root/'website/public/data/experiments.json').read_bytes())
        self.assertEqual(data['cohort']['selection_sha256'],canonical['selection_sha256'])
        self.assertEqual(data['cohort']['case_count'],47)
        self.assertEqual([r['model'] for r in data['records']],canonical['models'])
        for r in data['records']:
            self.assertEqual(r['caseCount'],47)
            self.assertEqual(r['episodes'],282)
            self.assertEqual(r['scope'],'main_experiment_47')
            self.assertNotIn('splits',r)
            self.assertLessEqual(r['completedCases'],47)
            self.assertLessEqual(r['scored'],282)
            if r['completedCases']<47:
                for name in ['linear','async','drs']: self.assertIsNone(r[name])

    def test_theme_macro_and_cohort_membership_not_split(self):
        values=scores(); values[('outside::seed-1','async',0)]={'score_status':'scored','base_task_score':1,'async_drs':1}
        result=exporter.aggregate_model('model',cohort(),values)
        self.assertEqual(result['completedCases'],3)
        self.assertEqual(result['scored'],18)
        self.assertEqual(result['drs'],0.5) # themes equally weighted, not cases or episodes
        self.assertEqual(result['linear'],0.5)
        self.assertEqual(result['themeMetrics']['two']['completedCases'],2)
        self.assertEqual(result['themeMetrics']['one']['linear'],0)
        self.assertEqual(result['executionStatus'],'unknown')
        self.assertEqual(result['coverageStatus'],'complete')
        self.assertIsNone(result['resources']['async']['tokens']['mean'])
        self.assertFalse(result['published'])
        self.assertNotIn('DO-NOT-EXPORT',json.dumps(result))
        self.assertNotIn('private_trace',json.dumps(result))
        self.assertNotIn('split',result)

    def test_incomplete_scores_do_not_become_full_cohort_scores_or_zero(self):
        values=scores(); values[('c::seed-1','async',2)]['score_status']='unscored'
        result=exporter.aggregate_model('model',cohort(),values)
        self.assertEqual(result['completedCases'],2)
        self.assertEqual(result['scored'],17)
        self.assertIsNone(result['drs'])
        self.assertEqual(result['observedDrs'],0.5)
        self.assertEqual(result['coverageStatus'],'incomplete')
        self.assertEqual(result['themeMetrics']['two']['completedCases'],1)
        values[('a::seed-1','async',0)]['async_drs']=None
        self.assertEqual(exporter.aggregate_model('model',cohort(),values)['completedCases'],1)

    def test_missing_modes_and_nonfinite_metrics_are_incomplete(self):
        values=scores(); del values[('a::seed-1','linear',0)]
        values[('b::seed-1','async',0)]['async_drs']=float('nan')
        result=exporter.aggregate_model('model',cohort(),values)
        self.assertEqual(result['completedCases'],1)
        self.assertIsNone(result['linear'])

    def test_score_identity_and_manifest_binding_are_checked(self):
        ep={'case_id':'a','instance_id':'seed-1','episode_id':'episode-1','execution_mode':'async','repeat':0,'model':'model','agent_seed':123,'counterfactual_pair_id':'pair','guidance':'incentive'}
        score=bound_score(ep,'digest'); manifest=bound_manifest([ep])
        exporter.validate_score(score,ep,'digest',manifest)
        with self.assertRaises(ValueError):
            exporter.validate_score({**score,'case_id':'b'},ep,'digest',manifest)
        with self.assertRaises(ValueError):
            exporter.validate_score(score,ep,'different',manifest)

        for field,value in [('evaluation_contract_version','old'),('evaluation_contract_sha256','wrong'),
                            ('agent_seed',456),('case_sha256','wrong'),('score_policy_version','old'),
                            ('conformance_passed',False),('protocol_valid',False),('runtime_mode','simulation'),
                            ('leaderboard_ineligibility_reasons',['workspace_not_container_clone']),
                            ('leaderboard_ineligibility_reasons',[])]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                exporter.validate_score({**score,field:value},ep,'digest',manifest)

    def test_duplicate_attempt_is_rejected(self):
        seen={('a::seed-1','async',0):{}}
        with self.assertRaises(ValueError):
            exporter.add_episode(seen,('a::seed-1','async',0),{})

    def test_reader_excludes_non_cohort_cases_and_non_main_models(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            directory=root/'artifacts/experiments/batch-model-test'
            directory.mkdir(parents=True)
            selected={'case_id':'a','instance_id':'seed-1','episode_id':'selected','execution_mode':'async','repeat':0,'model':'model','agent_seed':123,'counterfactual_pair_id':'pair','guidance':'incentive'}
            outside={**selected,'case_id':'outside','episode_id':'outside'}
            manifest=bound_manifest([selected,outside])
            raw=json.dumps(manifest).encode()
            (directory/'manifest.json').write_bytes(raw)
            score_path=directory/'runs/selected/score.json'
            score_path.parent.mkdir(parents=True)
            score_path.write_text(json.dumps(bound_score(selected,hashlib.sha256(raw).hexdigest())))
            # Even malformed score data outside the selected cohort must not be read.
            outside_path=directory/'runs/outside/score.json';outside_path.parent.mkdir(parents=True);outside_path.write_text('not score json')
            excluded=root/'artifacts/experiments/batch-not-main-test';excluded.mkdir()
            (excluded/'manifest.json').write_text(json.dumps({**manifest,'model':'not-main'}))
            records,_,_=exporter.read_experiments(root,cohort())
            self.assertEqual(set(records),{'model'})
            self.assertEqual(set(records['model']),{('a::seed-1','async',0)})

    def test_incompatible_pair_seeds_are_rejected(self):
        from async_rbench.main_experiment import validate_bindings
        ep={'case_id':'a','instance_id':'seed-1','repeat':0,'agent_seed':123,
            'counterfactual_pair_id':'pair','guidance':'incentive'}
        manifest=bound_manifest([ep])
        with self.assertRaisesRegex(ValueError,'pair binding'):
            validate_bindings(manifest,cohort(),[ep,{**ep,'agent_seed':456}])
        with self.assertRaisesRegex(ValueError,'contract'):
            validate_bindings({**manifest,'evaluation_contract_sha256':'wrong'},cohort(),[ep])

    def test_single_participant_run_uses_all_47_and_checks_pair_configuration(self):
        root=Path(__file__).resolve().parents[2]
        canonical=exporter.load_main_cohort(root)
        episodes=[]
        for key in canonical['instances']:
            case,instance=key.split('::')
            for mode in ['linear','async']:
                for repeat in range(3):
                    episodes.append({'case_id':case,'instance_id':instance,'execution_mode':mode,'repeat':repeat,
                        'model':'participant-model','episode_id':f'{case}-{mode}-{repeat}',
                        'agent_seed':repeat+1,'counterfactual_pair_id':f'{case}-{repeat}',
                        'guidance':'incentive','split':canonical['splits'][key]})
        manifest={**bound_manifest(episodes),'model':'participant-model',
            'evaluation_contract_sha256':canonical['evaluation_contract_sha256'],
            'paper_eval_selection':{'cohort':canonical['id'],'selection_sha256':canonical['selection_sha256']}}
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'manifest.json'; raw=json.dumps(manifest).encode(); path.write_bytes(raw)
            for ep in episodes:
                score=bound_score(ep,hashlib.sha256(raw).hexdigest())
                score['evaluation_contract_sha256']=canonical['evaluation_contract_sha256']
                score['base_task_score']=score['async_drs']=1
                score['child_pool_id']=None
                score_path=path.parent/'runs'/ep['episode_id']/'score.json'
                score_path.parent.mkdir(parents=True)
                score_path.write_text(json.dumps(score))
            record=exporter.export(root,path)['records'][0]
            self.assertEqual(record['model'],'participant-model')
            self.assertEqual(record['completedCases'],47)
            self.assertEqual(record['scored'],282)
            self.assertEqual(record['drs'],1)
            # Historical pool labels are not a main-experiment condition.
            score['child_pool_id']='a-different-historical-label'
            score_path.write_text(json.dumps(score))
            self.assertEqual(exporter.export(root,path)['records'][0]['completedCases'],47)
            score['resource_policy_sha256']='different-policy'
            score_path.write_text(json.dumps(score))
            with self.assertRaisesRegex(ValueError,'paired score configuration'):
                exporter.export(root,path)

if __name__=='__main__': unittest.main()
