const labels={
  episode_started:['运行开始','Episode started'],
  child_spawned:['创建子任务','Child created'],
  child_started:['子任务开始','Child started'],
  main_action:['主代理动作','Main-agent action'],
  main_action_finished:['动作返回','Action returned'],
  child_completed:['子任务返回','Child returned'],
  result_delivery_evaluator_fact:['交付观测','Delivery observation'],
  result_delivered:['结果交付','Result delivered'],
  result_available:['结果就绪','Result available'],
  adapter_queued:['进入呈现队列','Queued for presentation'],
  result_presented:['结果呈现','Result presented'],
  child_path_promotion_result:['文件转移结果','File transfer result'],
  finish_invoked:['请求结束运行','Finish requested'],
  episode_ended:['运行结束','Episode ended'],
  child_cancelled:['子任务取消','Child cancelled'],
};
export const eventLabel=(type,language)=>labels[type]?.[language==='en'?1:0]||type;
