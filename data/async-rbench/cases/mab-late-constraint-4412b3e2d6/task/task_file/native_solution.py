from dataclasses import dataclass,asdict
@dataclass(frozen=True)
class WatchOffer: revision:int; actor:str; price:float; battery_age_days:int; guarantee_months:int; quantity:int; consolidated:bool
class DiverWatchBargaining:
 def __init__(self):self.reference_price=68.99;self.ledger=[];self.agreement=None
 @property
 def revision(self):return len(self.ledger)
 def offer(self,actor,price,battery_age_days,guarantee_months,quantity,consolidated,expected_revision):
  if expected_revision!=self.revision:raise RuntimeError('stale offer')
  if self.agreement:raise RuntimeError('closed')
  if actor not in {'buyer','seller'} or price<=0 or battery_age_days<0 or guarantee_months<0 or quantity<=0:raise ValueError('invalid terms')
  x=WatchOffer(self.revision+1,actor,float(price),battery_age_days,guarantee_months,quantity,bool(consolidated));self.ledger.append(x);return x
 def seller_counter(self,expected_revision):return self.offer('seller',62,90,12,50,True,expected_revision)
 def accept(self,expected_revision):
  if expected_revision!=self.revision or not self.ledger:raise RuntimeError('stale acceptance')
  x=self.ledger[-1]
  if (x.price,x.battery_age_days,x.guarantee_months,x.quantity,x.consolidated)!=(62,90,12,50,True):raise ValueError('incomplete counter')
  self.agreement=x;return x
 def audit(self):return {'ledger':[asdict(x) for x in self.ledger],'chronological':[x.revision for x in self.ledger]==list(range(1,self.revision+1)),'agreement':asdict(self.agreement) if self.agreement else None}
