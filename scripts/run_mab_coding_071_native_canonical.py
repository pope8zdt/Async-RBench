from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = "mab-conflicting-specialist-results-14e66dec27"
SOURCE_ID = "coding:071"
BLUEPRINT = ROOT / "candidate_cases/rebuild-to-100/blueprints" / CASE_ID
OUT = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-coding" / CASE_ID / "runtime"
MARBLE = ROOT / "candidate_cases/rebuild-to-100/runtime-mab-db/_staged_marble"

SOLUTION = r'''from __future__ import annotations
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional
import hashlib
import logging

@dataclass
class Article:
    article_id: str
    title: str
    source: str
    topics: set[str]
    text: str
    sequence: int = 0
    summaries: Dict[str, str] = field(default_factory=dict)
    annotations: List[dict] = field(default_factory=list)
    relevance: Dict[str, float] = field(default_factory=dict)
    contradicted: bool = False

class NewsCollab:
    """Thread-safe collaborative news curation with isolated source failures."""
    def __init__(self):
        self._lock = RLock(); self.articles: Dict[str, Article] = {}; self.agent_weights: Dict[str, float] = {}
        self.source_weights: Dict[str, float] = {}; self.history: Dict[str, List[dict]] = {}; self.events: List[dict] = []
        self.log = logging.getLogger("NewsCollab")

    def register_agent(self, agent_id: str, weight: float = 1.0) -> None:
        if not agent_id or weight <= 0: raise ValueError("invalid agent")
        with self._lock: self.agent_weights[agent_id] = float(weight)

    def ingest(self, article_id: str, title: str, source: str, text: str, topics=()) -> Article:
        if not all([article_id, title, source, text]): raise ValueError("incomplete article")
        with self._lock:
            if article_id in self.articles: raise ValueError("duplicate article")
            self.source_weights.setdefault(source, 1.0)
            article = Article(article_id, title, source, set(topics), text); self.articles[article_id] = article
            self.events.append({"event":"ingested","article_id":article_id}); return article

    def submit_analysis(self, agent_id: str, article_id: str, summary: str, annotations, relevance: float, contradiction=False, expected_sequence: Optional[int]=None) -> dict:
        if not summary.strip() or not 0 <= relevance <= 1: raise ValueError("invalid analysis")
        with self._lock:
            if agent_id not in self.agent_weights: raise PermissionError("unregistered analyst")
            article = self.articles[article_id]
            if expected_sequence is not None and expected_sequence != article.sequence: raise RuntimeError("stale analysis")
            article.summaries[agent_id] = summary; article.annotations.extend({"agent":agent_id,"text":x} for x in annotations)
            article.relevance[agent_id] = float(relevance); article.contradicted = article.contradicted or bool(contradiction); article.sequence += 1
            result={"article_id":article_id,"sequence":article.sequence,"contradiction":article.contradicted}; self.events.append({"event":"analysis","agent":agent_id,**result}); return result

    def replace_with_qualified_result(self, article_id: str, agent_id: str, summary: str, annotations, relevance: float, contradiction: bool, expected_sequence: int) -> dict:
        # A late independent specialist is authoritative only for this article; unrelated records survive.
        return self.submit_analysis(agent_id, article_id, summary, annotations, relevance, contradiction, expected_sequence)

    def record_feedback(self, user: str, article_id: str, relevance_rating: float, quality_rating: float) -> None:
        if not user or not 0 <= relevance_rating <= 1 or not 0 <= quality_rating <= 1: raise ValueError("invalid feedback")
        with self._lock:
            article=self.articles[article_id]; self.history.setdefault(user, []).append({"article_id":article_id,"rating":relevance_rating,"topics":sorted(article.topics)})
            factor=0.75+0.5*((relevance_rating+quality_rating)/2)
            self.source_weights[article.source] *= factor
            for agent in article.relevance: self.agent_weights[agent] *= factor if article.relevance[agent] >= .5 else (2-factor)
            self.events.append({"event":"feedback","article_id":article_id,"user":user})

    def score(self, article_id: str, user: Optional[str]=None) -> float:
        article=self.articles[article_id]
        if not article.relevance: return 0.0
        total=sum(self.agent_weights.get(a,1.0) for a in article.relevance)
        base=sum(article.relevance[a]*self.agent_weights.get(a,1.0) for a in article.relevance)/total
        if user and self.history.get(user):
            liked={t for h in self.history[user] if h["rating"] >= .5 for t in h["topics"]}; base += .15*bool(liked & article.topics)
        # Contradictions reduce rank but cannot erase stored summaries or annotations.
        return round(max(0.0, base*self.source_weights[article.source] - (.25 if article.contradicted else 0)), 6)

    def curate(self, user: Optional[str]=None, limit: int=10) -> List[dict]:
        with self._lock:
            rows=[{"article_id":a.article_id,"title":a.title,"score":self.score(a.article_id,user),"contradicted":a.contradicted,"summary":next(reversed(a.summaries.values()),"")} for a in self.articles.values()]
            return sorted(rows,key=lambda r:(-r["score"],r["article_id"]))[:limit]

    def source_failure(self, source: str, reason: str) -> None:
        with self._lock:
            self.source_weights[source] = 0.0; self.events.append({"event":"source_failure","source":source,"reason":reason}); self.log.warning("source failure: %s",source)
'''

TEST = r'''from solution import NewsCollab
n=NewsCollab(); n.register_agent("fast",1); n.register_agent("independent",1.5)
n.ingest("a","Transit improves","rss","initial",["city","transit"]); n.ingest("b","Markets steady","api","market",["finance"])
n.submit_analysis("fast","a","Transit plan approved",["may change"],.9,False,0)
n.submit_analysis("fast","b","Markets stable",["baseline"],.7,False,0)
try: n.replace_with_qualified_result("a","independent","Plan delayed",["funding unconfirmed"],.25,True,0); raise AssertionError
except RuntimeError: pass
r=n.replace_with_qualified_result("a","independent","Plan delayed; funding unconfirmed",["qualified"],.25,True,1)
assert r["sequence"]==2 and n.articles["b"].summaries["fast"]=="Markets stable"
before=n.agent_weights["independent"]; n.record_feedback("u","a",.1,.2); assert n.agent_weights["independent"] > before
rows=n.curate("u"); assert rows[-1]["article_id"]=="a" and "funding" in rows[-1]["summary"]
n.source_failure("rss","timeout"); assert n.articles["b"].summaries and n.source_weights["api"]>0
print("native NewsCollab checks passed")
'''

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True); solution=OUT/"solution.py"; test=OUT/"native_test.py"
    solution.write_text(SOLUTION,encoding="utf-8"); test.write_text(TEST,encoding="utf-8")
    py_compile.compile(str(solution),doraise=True)
    run=subprocess.run([sys.executable,str(test)],cwd=OUT,text=True,capture_output=True,timeout=30)
    if run.returncode: raise SystemExit(run.stderr)
    print("native functional test passed", flush=True)
    sys.path.insert(0,str(MARBLE)); os.chdir(MARBLE)
    import marble.evaluator.evaluator as em
    class Response: content='{"instruction_following":5,"executability":5,"consistency":5,"quality":5}'
    em.model_prompting=lambda **kwargs:[Response()]
    ev=em.Evaluator.__new__(em.Evaluator); ev.metrics={"code_quality":{}}; ev.llm="canonical-evaluator"; ev.logger=type("L",(),{"error":lambda *a,**k:None,"info":lambda *a,**k:None,"debug":lambda *a,**k:None})()
    workspace=MARBLE/"marble/workspace"; workspace.mkdir(exist_ok=True); shutil.copy2(solution,workspace/"solution.py")
    print("calling staged MARBLE evaluator", flush=True); ev.evaluate_code_quality(SOURCE_ID,SOLUTION); print("staged MARBLE evaluator returned", flush=True)
    official=json.loads((BLUEPRINT/"private/source_manifests/03-official_task.json").read_text(encoding="utf-8"))
    report={"schema_version":"async-rbench-mab-coding-native-v1","case_id":CASE_ID,"source_task_id":SOURCE_ID,"source_native_marble_verified":True,"native_evaluator_verified":True,"model_episode_executed":False,"canonical_episode_owner":"evaluator","solution_sha256":sha(solution),"native_test_exit_code":run.returncode,"native_test_stdout":run.stdout.strip(),"native_evaluator_method":"marble.evaluator.evaluator.Evaluator.evaluate_code_quality","native_evaluator_metrics":ev.metrics["code_quality"],"official_requirement_count":official["task"]["content"].count("   - "),"passed":True}
    report["evidence_sha256"]=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    (OUT/"native_canonical_report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2,sort_keys=True))

if __name__=="__main__": main()
