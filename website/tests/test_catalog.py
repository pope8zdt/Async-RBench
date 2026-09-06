import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('catalog',Path(__file__).parents[1]/'scripts/catalog.py')
catalog=importlib.util.module_from_spec(spec);spec.loader.exec_module(catalog)

class CatalogTests(unittest.TestCase):
    def test_repository_totals_match_current_registry_and_each_theme(self):
        root=Path(__file__).resolve().parents[2]
        data=catalog.build_catalog(root)
        registry=json.loads((root/'cases/registry.json').read_bytes())['case_families']
        self.assertEqual(data['caseCount'],len(registry))
        self.assertEqual(data['instanceCount'],sum(len(c['instances']) for c in registry))
        self.assertEqual(sum(t['caseCount'] for t in data['themes']),data['caseCount'])
        self.assertEqual(sum(t['instanceCount'] for t in data['themes']),data['instanceCount'])
        self.assertEqual(len(data['themes']),8)
        self.assertNotIn('private_case',json.dumps(data))
        self.assertNotIn('validator',json.dumps(data))

    def test_catalog_updates_when_registered_case_is_added(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'cases').mkdir()
            (root/'event_taxonomy.json').write_text(json.dumps({'event_themes':[{'id':'one'},{'id':'two'}]}))
            records=[]
            for case,theme in [('a','one'),('b','two')]:
                p=root/'cases'/case/'private';p.mkdir(parents=True)
                (p/'private_case.yaml').write_text('classification: {primary_event_theme: '+theme+'}\nprivate_secret: DO-NOT-PUBLISH')
                records.append({'case_id':case,'instances':[{'instance_id':'seed-1','path':'.'}]})
                (root/'cases/registry.json').write_text(json.dumps({'case_families':records}))
                result=catalog.build_catalog(root)
                self.assertEqual(result['caseCount'],len(records))
                self.assertNotIn('DO-NOT-PUBLISH',json.dumps(result))
            records.append(records[0])
            (root/'cases/registry.json').write_text(json.dumps({'case_families':records}))
            with self.assertRaisesRegex(ValueError,'duplicate'):
                catalog.build_catalog(root)

if __name__=='__main__':unittest.main()
