import random
DOMAIN = 'ecosphere_manager'
DERIVE_HEALTH = True
PRESERVE_COLLABORATION = True
EVENT_SCHEMA = 'ecosystem_tick_v2'

class EcoSphereManager:
    def __init__(self): self.species={}; self.resources={'food':100.0,'water':100.0}; self.climate=0.0; self.pollution=0.0; self.health=50.0; self.messages=[]; self.habitats={}; self.history=[]
    def add_species(self,name,population,limit,food_need,habitat): self.species[name]={'population':float(population),'limit':float(limit),'food_need':float(food_need)}; self.habitats[name]=habitat
    def collaborate(self,player,message):
        if PRESERVE_COLLABORATION: self.messages.append((player,message))
    def tick(self,seed,climate_delta=0.0,pollution_delta=0.0,disaster=0.0):
        rng=random.Random(seed); old={'species':{k:dict(v) for k,v in self.species.items()},'resources':dict(self.resources),'health':self.health}
        next_species={}
        food=self.resources['food']
        for name,data in sorted(self.species.items()):
            capacity=min(data['limit'],max(0.0,food/max(data['food_need'],0.1))); growth=(0.04-rng.random()*0.01)*(1-max(0.0,self.pollution+pollution_delta)/100); population=max(0.0,min(capacity,data['population']*(1+growth)-disaster)); next_species[name]={**data,'population':round(population,3)}; food=max(0.0,food-population*data['food_need']*0.05)
        water=max(0.0,self.resources['water']-abs(self.climate+climate_delta)*2-disaster)
        new_pollution=max(0.0,self.pollution+pollution_delta); biodiversity=sum(1 for s in next_species.values() if s['population']>0)
        derived=max(0.0,min(100.0,50+biodiversity*10+food*.1+water*.1-new_pollution*.5-disaster))
        self.species=next_species; self.resources={'food':round(food,3),'water':round(water,3)}; self.climate+=climate_delta; self.pollution=new_pollution
        if DERIVE_HEALTH: self.health=round(derived,3)
        self.history.append({'seed':seed,'before':old,'after':self.snapshot()}); return self.snapshot()
    def snapshot(self): return {'species':{k:dict(v) for k,v in self.species.items()},'resources':dict(self.resources),'climate':self.climate,'pollution':self.pollution,'health':self.health}
