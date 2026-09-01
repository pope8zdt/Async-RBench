DOMAIN = 'price_tracker_collaborator'
CONVERT_CURRENCIES = True
PRESERVE_GROUP_SHARING = True
EVENT_SCHEMA = 'normalized_quote_v2'
RATES={'USD':1.0,'EUR':1.2,'GBP':1.3}

class PriceTrackerCollaborator:
    def __init__(self): self.users={}; self.groups={}; self.watchlists={}; self.notifications=[]; self.history={}
    def register(self,email,password):
        if '@' not in email or len(password)<4: raise ValueError('invalid credentials')
        self.users[email]={'password':'hash:'+password,'preferences':{'email':True,'in_app':True}}; self.watchlists[email]={}
    def create_group(self,name,owner): self.groups[name]={owner}
    def join_group(self,name,user): self.groups[name].add(user)
    def watch(self,user,product_id,url,threshold,currency='USD'):
        if not url.startswith(('http://','https://')): raise ValueError('invalid URL')
        self.watchlists[user][product_id]={'url':url,'threshold':float(threshold),'currency':currency}
    def best_quote(self,quotes,now,max_age=300):
        valid=[q for q in quotes if q['available'] and now-q['observed_at']<=max_age]
        def comparable(q): return q['price']*RATES[q['currency']] if CONVERT_CURRENCIES else q['price']
        return min(valid,key=lambda q:(comparable(q),q['retailer'])) if valid else None
    def ingest_quotes(self,product_id,quotes,now):
        best=self.best_quote(quotes,now); self.history.setdefault(product_id,[]).extend(quotes)
        if best:
            usd=best['price']*RATES[best['currency']] if CONVERT_CURRENCIES else best['price']
            for user,items in self.watchlists.items():
                if product_id in items and usd<=items[product_id]['threshold']*RATES[items[product_id]['currency']]: self.notifications.append((user,'threshold_met',product_id,best['retailer']))
        return best
    def share_alert(self,group,sender,product_id):
        if not PRESERVE_GROUP_SHARING: return []
        sent=[]
        for member in sorted(self.groups[group]-{sender}): self.notifications.append((member,'shared_alert',product_id,sender)); sent.append(member)
        return sent
