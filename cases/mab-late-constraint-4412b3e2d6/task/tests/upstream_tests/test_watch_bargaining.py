import importlib.util
import json
import sys
from pathlib import Path

OUT = Path('/app/output_data')

def model():
    spec = importlib.util.spec_from_file_location('watch_bargaining_solution', OUT / 'solution.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.DiverWatchBargaining()

def test_stale_counter_is_rejected():
    table = model()
    table.offer('buyer', 60, 90, 12, 50, True, 0)
    try:
        table.seller_counter(0)
        raise AssertionError('stale counter unexpectedly accepted')
    except RuntimeError:
        pass

def test_qualified_counter_terms_are_exact():
    table = model()
    table.offer('buyer', 60, 90, 12, 50, True, 0)
    counter = table.seller_counter(1)
    assert (counter.price, counter.battery_age_days, counter.guarantee_months, counter.quantity, counter.consolidated) == (62, 90, 12, 50, True)
    receipt = json.loads((OUT / 'event_receipt.json').read_text())
    assert receipt['qualified_result'] == {'price': 62, 'battery_age_days': 90, 'guarantee_months': 12, 'quantity': 50, 'consolidated': True}

def test_only_qualified_counter_can_close():
    table = model()
    table.offer('buyer', 60, 90, 12, 50, True, 0)
    table.seller_counter(1)
    agreement = table.accept(2)
    assert agreement.actor == 'seller' and agreement.price == 62

def test_audit_is_chronological():
    table = model()
    table.offer('buyer', 60, 90, 12, 50, True, 0)
    table.seller_counter(1)
    table.accept(2)
    audit = table.audit()
    assert audit['chronological'] is True and audit['agreement']['quantity'] == 50
