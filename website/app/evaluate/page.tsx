import { EvaluateForm } from '@/components/evaluate-form';
import { T } from '@/components/preferences';
import { Suspense } from 'react';
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>
          <T zh="开始评测" en="Evaluate" />
        </h1>
        <p>
          <T
            zh="配置模型，下载脚本，在本地运行。"
            en="Configure a model. Download the script. Run locally."
          />
        </p>
      </div>
      <Suspense
        fallback={
          <p>
            <T zh="加载配置…" en="Loading configuration…" />
          </p>
        }
      >
        <EvaluateForm />
      </Suspense>
    </div>
  );
}
