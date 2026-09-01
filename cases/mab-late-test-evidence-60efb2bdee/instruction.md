Software Development Task:

Please write a program called OfficeTaskScheduler that helps manage and schedule tasks for multiple team members within an office environment. OfficeTaskScheduler is a task management system that allows users to create, assign, and track tasks, as well as set deadlines and priorities, and monitor the progress of each task.
1. Implementation requirements:
   - The program should allow multiple users to log in and manage their tasks.
   - Each user should be able to create new tasks, assign them to other team members, set deadlines, and priorities.
   - The system should provide a dashboard for each user to view their assigned tasks, including the status (e.g., pending, in progress, completed), deadline, and priority level.
   - The program should include a notification system to alert users about upcoming deadlines and task assignments.
   - The system should allow users to update the status of their tasks and add comments or notes.
   - The program should generate reports on task completion rates, overdue tasks, and task distribution among team members.
   - Test cases should include scenarios for creating and assigning tasks, updating task statuses, receiving notifications, and generating reports.
   - Edge cases should test the system's behavior when a user tries to assign a task to a non-existent user, set a deadline in the past, or access tasks assigned to other users without proper authorization.


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
Build OfficeTaskScheduler with users, task creation and assignment, deadlines, priorities, dashboards, notifications, status changes, comments, and reports. Three workstreams establish task and reporting behavior. A fourth evaluator-owned edge-test completion may be replayed. Deduplicate it by evidence identity, enforce nonexistent-user, past-deadline and unauthorized-access cases, preserve valid task state, and reverify overdue and completion reports.
