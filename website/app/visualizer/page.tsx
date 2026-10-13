import { TrajectoryVisualizer } from '@/components/trajectory-visualizer';
import { T } from '@/components/preferences';

export default function VisualizerPage() {
  return (
    <div className="page-wrap visualizer-page">
      <header className="page-title visualizer-title">
        <span className="eyebrow">
          <T zh="轨迹可视化" en="Trajectory visualizer" />
        </span>
        <h1>
          <T zh="回放一次评测" en="Replay an evaluation" />
        </h1>
        <p>
          <T
            zh="在浏览器本地查看异步事件、子任务状态与结果交付顺序。"
            en="Inspect asynchronous events, child status and result delivery order locally in your browser."
          />
        </p>
      </header>
      <TrajectoryVisualizer />
    </div>
  );
}
