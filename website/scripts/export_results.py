"""Public website entry point for the shared main-47 aggregator."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from async_rbench.main_results import (  # noqa: F401
    load_main_cohort, aggregate_model, validate_score, add_episode, read_experiments, export, main,
)
if __name__ == '__main__':
    main()
