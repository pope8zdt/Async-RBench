Software Development Task:

Please write a multiplayer online battle arena (MOBA) game called Galactic Conquest. Galactic Conquest is a MOBA game that allows players to team up and engage in strategic battles against AI-controlled enemies and other player teams. The game features a variety of customizable characters, each with unique abilities, and a dynamic environment that changes with each level. The objective is to capture and hold key points on the map while defending your own territory.
1. Implementation requirements:
   - Develop a character creation system that allows players to select and customize their characters, including choosing from a set of unique abilities. This system must be completed before the game can be tested for balance and player experience.
   - Create an AI system that controls enemy characters and manages the behavior of AI-controlled teams. This AI system should be designed to adapt to player actions and provide a challenging experience. The AI system must be developed and tested before integrating it with the multiplayer components.
   - Implement a map system that generates different environments for each level, including key points that players must capture and defend. The map system should also include features such as destructible environments and power-ups. The map system must be functional and tested for gameplay balance before the multiplayer features are added.
   - Design a multiplayer framework that supports team-based gameplay, including matchmaking, in-game chat, and real-time synchronization of player actions. This framework must be built on top of the character creation, AI, and map systems, and must be thoroughly tested for stability and performance.
   - Develop a scoring and progression system that tracks player achievements, awards points for capturing and holding key points, and provides rewards for winning matches. This system should be integrated after the core gameplay features are complete and tested.
   - Create a user interface (UI) that provides players with essential information, such as character stats, map layout, and team status. The UI must be designed and implemented to enhance the player experience and should be the final step in the development process.


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
First persist validated character customization and adaptive-AI state while multiplayer remains blocked on map validation. The harness then delivers an authoritative fixed-seed map checkpoint covering objective placement, destructible terrain, power-ups, and balance invariants. Consume that exact receipt, release matchmaking/chat/action synchronization only for the validated map revision, reject stale synchronized actions, preserve accepted capture scores and progression, and write solution.py plus a receipt-bound closure under /app/output_data.
