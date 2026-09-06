import { EvaluateForm } from '@/components/evaluate-form';
import { Suspense } from 'react';
export const metadata = { title: '开始评测' };
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <div className="eyebrow">EVALUATION WORKSPACE</div>
        <h1>开始一次评测</h1>
        <p>在网页生成配置，在你自己的电脑运行评测，再提交结果供审核。</p>
      </div>
      <Suspense fallback={<p>正在准备本地评测配置…</p>}>
        <EvaluateForm />
      </Suspense>
    </div>
  );
}
