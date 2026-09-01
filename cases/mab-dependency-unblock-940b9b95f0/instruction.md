Software Development Task:

Please write a system called Multi-Agent Transport Planner (MATP) that dynamically coordinates and optimizes multi-modal transportation plans for users based on real-time data and user preferences. MATP is a transportation coordination system that integrates data from various sources, including traffic conditions, public transportation schedules, and weather forecasts, to provide users with the most efficient and personalized travel plans.
1. Implementation requirements:
   - MATP should allow users to input their starting location, destination, and preferred modes of transportation (e.g., public transport, private vehicles, cycling, walking).
   - The system should dynamically adjust the suggested routes and modes of transportation based on real-time traffic conditions, public transportation delays, and weather changes.
   - MATP should provide users with multiple route options, including the fastest, the most cost-effective, and the most environmentally friendly, and allow users to select their preferred option.
   - The system should include a feedback mechanism where users can report issues (e.g., delays, road closures) and provide ratings for the suggested routes, which will be used to improve future recommendations.
   - MATP should support multi-agent collaboration, enabling it to coordinate routes for multiple users traveling to the same destination, optimizing the overall travel experience and reducing congestion.
   - The system should have a user-friendly interface that displays real-time updates and allows users to easily modify their plans on the go.


2. Project structure:
   - solution.py (main implementation)

3. Development process:
   - Developer: Create the code.
   - Developer: Revise the code.
   - Developer: Optimize the code.

If there are multiple files, please put them all in solution.py, but remember to add the file name in the following format:
```python
# file_name_1.py
# your code here

# file_name_2.py
# your code here

# file_name_3.py
# your code here
```

Please work together to complete this task following software engineering best practices.

The final deliverable should include:
solution.py

ASYNC-RBENCH EXTENSION
Persist static route candidates, preferences, feedback, and collaboration state while normalized conditions fail to arrive. The harness then delivers a fresh timestamped traffic/transit/weather snapshot. Re-delegate the failed dependency, adjust leg costs, recompute fastest/cost/eco rankings deterministically, preserve feedback, and close on the exact receipt.
