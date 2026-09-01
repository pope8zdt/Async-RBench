DOMAIN = 'food_chain'
TRAFFIC_AWARE = True

class FoodChain:
    def __init__(self): self.restaurants={}; self.orders={}; self.notifications=[]; self.feedback=[]
    def add_restaurant(self,rid,menu): self.restaurants[rid]={'menu':dict(menu)}
    def place_order(self,order_id,customer,rid,items,mode='delivery'):
        if mode not in {'delivery','pickup'}: raise ValueError('invalid mode')
        if any(i not in self.restaurants[rid]['menu'] for i in items): raise ValueError('unavailable item')
        self.orders[order_id]={'customer':customer,'restaurant':rid,'items':list(items),'mode':mode,'status':'placed','route':None}; self.notifications.append((customer,'placed')); return self.orders[order_id]
    def restaurant_decision(self,order_id,decision,available_items=None):
        if decision not in {'accept','reject','modify'}: raise ValueError('invalid decision')
        order=self.orders[order_id]
        if decision=='modify': order['items']=[i for i in order['items'] if i in set(available_items or [])]
        order['status']={'accept':'accepted','reject':'rejected','modify':'modified'}[decision]; self.notifications.append((order['customer'],order['status'])); return order
    def assign_courier(self,order_id,courier): self.orders[order_id].update(courier=courier,status='assigned')
    def replan(self,order_id,courier_locations,traffic):
        order=self.orders[order_id]; candidates=sorted(courier_locations, key=lambda c:(traffic.get(c,1) if TRAFFIC_AWARE else 1,c)); route=candidates; congestion=sum(traffic.get(c,1) for c in route) if TRAFFIC_AWARE else len(route); result={'route':route,'priority':'high' if congestion>len(route)*1.5 else 'normal','eta_minutes':10+5*congestion}; order.update(result); self.notifications.append((order.get('courier'),'route_updated')); return result
    def courier_status(self,order_id,status):
        if status not in {'picked_up','delivered'}: raise ValueError('invalid status')
        self.orders[order_id]['status']=status; self.notifications.append((self.orders[order_id]['customer'],status))
    def rate(self,order_id,restaurant_rating,delivery_rating): self.feedback.append({'order_id':order_id,'restaurant':restaurant_rating,'delivery':delivery_rating})
