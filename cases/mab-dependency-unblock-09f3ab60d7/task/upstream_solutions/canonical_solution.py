DOMAIN = 'macao'
EXCLUDE_NONEXECUTABLE = True

class MACAO:
    def coverage(self, source, covered_lines):
        lines=source.splitlines(); executable=[]
        for number,text in enumerate(lines,1):
            if EXCLUDE_NONEXECUTABLE and (not text.strip() or text.lstrip().startswith('#')): continue
            executable.append(number)
        statuses={n:('covered' if n in covered_lines else 'missed') for n in executable}
        percentage=round(100*sum(v=='covered' for v in statuses.values())/len(statuses),2) if statuses else 100.0
        heatmap={n:(1.0 if status=='covered' else 0.0) for n,status in statuses.items()}
        return {'statuses':statuses,'percentage':percentage,'heatmap':heatmap}

    def complexity(self, source):
        branches=sum(source.count(k) for k in ('if ','for ','while ','except ')); return {'cyclomatic':1+branches,'nesting_depth':max((len(x)-len(x.lstrip()))//4 for x in source.splitlines()) if source.splitlines() else 0,'duplication':0}

    def size(self, files):
        return {'files':len(files),'lines':sum(len(text.splitlines()) for text in files.values())}

    def integrate(self, coverage, complexity, size):
        if not coverage or not complexity or not size: raise RuntimeError('all analysis modules required')
        return {'coverage':coverage,'complexity':complexity,'size':size,'recommendations':['add tests'] if coverage['percentage']<100 else []}

    def recover_coverage(self, failure, source, covered_lines):
        if failure!='implicit_no_result': raise ValueError('unexpected failure')
        result=self.coverage(source,covered_lines); return {'recovery':'redelegated','result':result}
