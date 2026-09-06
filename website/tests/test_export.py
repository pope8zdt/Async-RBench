import importlib.util
import pathlib
import unittest

spec = importlib.util.spec_from_file_location('export_results', pathlib.Path(__file__).parents[1] / 'scripts/export_results.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

class ExportTests(unittest.TestCase):
    def test_only_public_summary_fields_leave_export(self):
        source = {'architecture_version':'11.0.0','rows':[{'model':'example','n':2,'scored_n':1,'split':'test','case_id':'secret-case'}], 'development_summary':{'linear_base_task_score':None,'async_base_task_score':0,'async_dynamic_replanning_score':0.5,'case_id':'secret-case','api_key':'secret','event_source':{'truth':'private'}}}
        result = exporter.project_result(source, 'a'*64, '2026-09-06')
        self.assertEqual(result['linear'],None)
        self.assertEqual(result['async'],0)
        self.assertFalse(result['published'])
        self.assertNotIn('secret',str(result))
        self.assertNotIn('case_id',str(result))
    def test_native_leaderboard_does_not_imply_publication(self):
        result = exporter.project_result({'rows':[], 'leaderboard':[{'model':'example','async_dynamic_replanning_score':1}]}, 'a'*64,'2026-09-06')
        self.assertFalse(result['published'])

if __name__ == '__main__': unittest.main()
