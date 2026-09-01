DOMAIN = 'multiserve'
PARTITION_BY_RESTAURANT = True
PRESERVE_CANCELLATION = True
EVENT_SCHEMA = 'suborder_logistics_v3'

class MultiServe:
    def __init__(self): self.restaurants={}; self.agents={}; self.orders={}; self.notifications=[]
    def add_restaurant(self,rid,menu,available=True): self.restaurants[rid]={'menu':set(menu),'available':available}
    def add_agent(self,agent,available=True): self.agents[agent]={'available':available}
    def place_order(self,order_id,user,items):
        groups={}
        for item in items:
            rid=item['restaurant'] if PARTITION_BY_RESTAURANT else 'combined'; groups.setdefault(rid,[]).append(item['item'])
        sub={rid:{'items':vals,'status':'pending'} for rid,vals in groups.items()}; self.orders[order_id]={'user':user,'suborders':sub,'status':'pending','canceled':False,'tasks':{}}; return sub
    def set_suborder_status(self,order_id,restaurant,status):
        if status not in {'pending','ready','failed'}: raise ValueError('invalid status')
        self.orders[order_id]['suborders'][restaurant]['status']=status; states=[x['status'] for x in self.orders[order_id]['suborders'].values()]
        self.orders[order_id]['status']='failed' if 'failed' in states else ('ready' if all(x=='ready' for x in states) else 'partially_ready')
        if self.orders[order_id]['status']=='ready': self.notifications.append((self.orders[order_id]['user'],'ready_for_pickup'))
        return self.orders[order_id]['status']
    def assign_deliveries(self,order_id):
        order=self.orders[order_id]
        if order['canceled'] and PRESERVE_CANCELLATION: return {}
        available=[a for a,v in sorted(self.agents.items()) if v['available']]
        for index,rid in enumerate(sorted(order['suborders'])):
            if not available: break
            order['tasks'][rid]={'agent':available[index%len(available)],'status':'assigned'}
        return order['tasks']
    def decline(self,order_id,restaurant):
        task=self.orders[order_id]['tasks'][restaurant]; self.agents[task['agent']]['available']=False; del self.orders[order_id]['tasks'][restaurant]; return self.assign_deliveries(order_id)
    def cancel(self,order_id): self.orders[order_id]['canceled']=True; self.orders[order_id]['status']='canceled'; self.orders[order_id]['tasks'].clear(); self.notifications.append((self.orders[order_id]['user'],'canceled'))
    def delivery_complete(self,order_id,restaurant):
        self.orders[order_id]['tasks'][restaurant]['status']='delivered'
        if all(t['status']=='delivered' for t in self.orders[order_id]['tasks'].values()): self.orders[order_id]['status']='delivered'; self.notifications.append((self.orders[order_id]['user'],'delivered'))
