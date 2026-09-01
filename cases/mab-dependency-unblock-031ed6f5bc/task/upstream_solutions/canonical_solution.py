DOMAIN = 'data_flow_coordinator'
REJECT_INVALID_ROWS = True

class DataFlowCoordinator:
    ORDER = ('ingestion','validation','transformation','export')
    def __init__(self):
        self.raw=[]; self.accepted=[]; self.rejected=[]; self.transformed=[]; self.exports=[]; self.seen_events=set(); self.stage='new'

    def ingest(self, source_type, rows):
        if source_type not in {'csv','excel','database'}: raise ValueError('unsupported source')
        self.raw=[dict(r, _source=source_type) for r in rows]; self.stage='ingestion'; return self.raw

    def validate(self):
        if self.stage!='ingestion': raise RuntimeError('ingestion required')
        self.accepted=[]; self.rejected=[]
        for row in self.raw:
            errors=[]
            if not row.get('id'): errors.append('missing_id')
            try: float(row.get('amount'))
            except (TypeError,ValueError): errors.append('invalid_amount')
            target=self.rejected if errors and REJECT_INVALID_ROWS else self.accepted
            target.append({'row':row,'errors':errors} if target is self.rejected else row)
        self.stage='validation'; return {'accepted':self.accepted,'rejected':self.rejected}

    def transform(self, rules):
        if self.stage!='validation': raise RuntimeError('validation required')
        rows=[dict(r) for r in self.accepted]
        if rules.get('uppercase_name'):
            for r in rows:
                if 'name' in r: r['name']=str(r['name']).upper()
        if rules.get('deduplicate'):
            seen=set(); rows=[r for r in rows if not (r['id'] in seen or seen.add(r['id']))]
        self.transformed=rows; self.stage='transformation'; return rows

    def export(self, output_format):
        if self.stage!='transformation': raise RuntimeError('transformation required')
        if output_format not in {'csv','excel','database'}: raise ValueError('unsupported output')
        artifact={'format':output_format,'rows':[dict(r) for r in self.transformed]}; self.exports.append(artifact); self.stage='export'; return artifact

    def consume_validation_completion(self, event_id, rules, output_format='csv'):
        if event_id in self.seen_events: return {'duplicate':True,'exports':len(self.exports)}
        self.seen_events.add(event_id); self.validate(); self.transform(rules); result=self.export(output_format); return {'duplicate':False,'artifact':result}
