Software Development Task:

Please write a software system called MultiAgent_Project_Manager. MultiAgent_Project_Manager is a project management tool that facilitates the coordination and tracking of tasks among multiple agents, ensuring that dependencies are respected and tasks are completed in the correct order. It provides a user-friendly interface for task creation, assignment, and monitoring, and it automatically updates the project status based on the completion of dependent tasks.
1. Implementation requirements:
   - The system should allow users to create projects and define tasks within those projects, specifying the task name, description, and deadlines.
   - Each task should have a list of dependencies, where certain tasks (e.g., Task A and Task B) must be completed before other tasks (e.g., Task C) can begin. The system should enforce these dependencies and prevent the start of dependent tasks until their prerequisites are completed.
   - The system should provide a dashboard for users to monitor the status of all tasks, including which tasks are pending, in progress, and completed. It should also highlight any tasks that are delayed or blocking progress.
   - The system should support user roles such as Project Manager, Team Lead, and Team Member, with different levels of access and responsibilities. For example, Project Managers can create and assign tasks, while Team Members can only view and update the status of their assigned tasks.
   - The system should send notifications to users when tasks are assigned, when dependencies are met, and when tasks are completed. These notifications should be configurable and can be sent via email or in-app messages.
   - The system should have a history log that tracks all changes to tasks, including assignments, status updates, and completion times, to help with project auditing and performance reviews.


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
Persist projects, tasks, assignments, dashboard state, notifications, and history while dependency semantics are provisional. The harness then delivers a complete cycle-safe dependency contract. Adopt transitive readiness, revise only affected task/dashboard states, preserve role and audit records, and close against the exact authority receipt.
