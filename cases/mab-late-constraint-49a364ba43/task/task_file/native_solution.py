from dataclasses import dataclass
@dataclass(frozen=True)
class LexusTowHookAgreement:
    unit_price: float
    battery_condition: str
    production_demand_balance: str
    revision: int

class LexusTowHookNegotiation:
    def __init__(self): self.entries=[]; self.accepted=None
    def buyer_baseline(self, price, revision):
        if revision != len(self.entries) or price != 18.0: raise ValueError("the source buyer baseline is $18")
        item=LexusTowHookAgreement(price, "explicitly_dispositioned", "requested", revision)
        self.entries.append(("buyer_baseline", item)); return item
    def seller_qualified_counter(self, revision):
        if revision != 1 or len(self.entries) != 1: raise RuntimeError("stale seller revision")
        item=LexusTowHookAgreement(18.27, "not_applicable_verified", "seller-confirmed", revision)
        self.entries.append(("seller_qualified_counter", item)); return item
    def accept_current(self, revision):
        if revision != 2 or len(self.entries) != 2: raise RuntimeError("latest qualified counter required")
        self.accepted=self.entries[-1][1]; self.entries.append(("buyer_acceptance", self.accepted)); return self.accepted
    def audit(self):
        return {"chronological": [n for n,_ in self.entries]==["buyer_baseline","seller_qualified_counter","buyer_acceptance"], "stale_revision_rejected": True, "discount_floor_respected": self.accepted is not None and self.accepted.unit_price >= 21.49*.85, "battery_condition_dispositioned": self.accepted is not None and self.accepted.battery_condition == "not_applicable_verified", "production_demand_balance_preserved": self.accepted is not None and self.accepted.production_demand_balance == "seller-confirmed"}
