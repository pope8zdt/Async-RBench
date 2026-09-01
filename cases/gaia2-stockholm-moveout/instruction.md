# Stockholm Move-Out (structure-derived)

The executable participant instruction is [task/task.yaml](task/task.yaml). This
case is a Async-RBench async-dynamic-replanning transformation of the official GAIA2
scenario `scenario_universe_21_xvc7uo` (lock commit
`78ea3bdbdeec2bdcd6afa542091`): a friend moving to Stockholm has a saved
apartment list in the RentAFlat app; the agent corrects that list against the
saved search, keeps watching a deterministic listing feed over a simulated
window, and sends the friend a Messages notification each time a newly listed
apartment that falls inside the saved search appears — while ignoring every
out-of-range or out-of-city listing. The notification predicate is derivable
only by reading the simulated apps under `task/task_file/app`. The local
container replaces the original environment simulator with a deterministic,
stateless event feed (`task/task_file/event_feed` + `scripts/read_events.py`).
Read the full contract in `task/task.yaml`; the maintained outcome contract is
in `task/tests/`.
