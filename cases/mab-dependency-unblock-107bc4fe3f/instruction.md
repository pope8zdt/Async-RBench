Software Development Task:

Please write a collaborative puzzle game called MultiAgentMaze. MultiAgentMaze is a multi-player puzzle game that requires players to work together to navigate through a complex maze by strategically moving blocks and creating paths. The game is designed to enhance teamwork and strategic thinking, with each player controlling a different aspect of the game environment.
1. Implementation requirements:
   - The game should support multiple players, each with a unique role (e.g., pathfinder, blocker, swapper).
   - The frontend should provide a real-time, interactive interface where players can see the maze, their roles, and the actions of other players.
   - The backend should manage the game state, including the positions of the blocks, the current paths, and the actions taken by each player.
   - The game should include a database to store player profiles, game history, and performance metrics.
   - Communication between the frontend and backend should be seamless, with real-time updates to reflect player actions and changes in the game state.
   - The game should include multiple levels with increasing difficulty, introducing new challenges and obstacles.
   - Players should be able to earn points and bonuses for successful collaboration and strategic play.
   - The game should provide feedback and hints to players to encourage effective teamwork and problem-solving.


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
The harness then delivers evaluator-owned asynchronous authority through the private event channel.
Build MultiAgentMaze with distinct cooperative roles, movable blocks, path finding, shared messages, progress persistence, tutorials, difficulty, and achievements. Three upstream workstreams establish the maze and collaboration state. A fourth evaluator-owned dependency adds an authoritative role-permission, optimistic-version, and collision protocol. Replan affected moves, reject stale or unauthorized operations, preserve existing state, and reverify a cooperative path to the exit.
