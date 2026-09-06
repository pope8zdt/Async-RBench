import { EvaluateForm } from '@/components/evaluate-form';
import { Suspense } from 'react';
export const metadata = { title: '开始评测' };
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>开始评测</h1>
        <p>填写模型信息，下载配置与脚本，在本地运行评测。</p>
      </div>
      <Suspense fallback={<p>正在准备本地评测配置…</p>}>
        <EvaluateForm />
      </Suspense>
    </div>
  );
}
