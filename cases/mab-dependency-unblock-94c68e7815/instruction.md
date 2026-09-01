Software Development Task:

Please write a system called Multi-Agent_Quest_Creator that allows multiple role-playing game players to collaboratively design and balance quests. Multi-Agent_Quest_Creator is a software system that enables players to work together to create, modify, and balance quests in a role-playing game, ensuring that the quests are challenging yet fair for all players involved.
1. Implementation requirements:
   - The system should allow multiple players to log in and collaborate in real-time on the design of a quest, including setting objectives, enemies, rewards, and difficulty levels.
   - The system should provide real-time feedback on the balance of the quest, suggesting adjustments to difficulty based on the combined input of player skills, enemy strengths, and quest objectives.
   - The system should adapt to user feedback by suggesting modifications to the quest parameters to better align with player preferences and game balance, such as adjusting the number of enemies, the type of enemies, or the rewards available.
   - The system should have a history feature that tracks changes made to the quest, allowing players to revert to previous versions if necessary.
   - The system should include a testing mode where players can simulate the quest to see how it plays out, providing data that can be used to further refine the quest.
   - The system should support the creation of different types of quests (e.g., combat, puzzle, exploration) and allow for the integration of custom content, such as player-created NPCs or items.
   - The system should provide tools for players to share their quests with the community, including options for rating and reviewing quests created by others.


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
Persist collaborative quest versions, history, testing, and community state while the balance child has failed implicitly. The harness then delivers structured difficulty, fairness, and ranked adjustments. Re-delegate balance, apply accepted adjustments as versioned edits, preserve revert/community records, and reverify stronger-enemy and reward mutations.
