Software Development Task:

Please write a software system called Office_Task_Collaborator. Office_Task_Collaborator is a collaborative task management system designed to help teams in an office environment efficiently manage and track tasks, deadlines, and responsibilities. It provides a centralized platform where team members can create, assign, and monitor tasks, set deadlines, and communicate with each other. The system supports multiple projects and integrates with calendar applications to ensure deadlines are met and tasks are completed on time.
1. Implementation requirements:
   - The system should allow users to create tasks with detailed descriptions, deadlines, and priority levels.
   - Users should be able to assign tasks to other team members and track the status of each task (e.g., not started, in progress, completed).
   - The system should provide a dashboard for each user to view their assigned tasks, upcoming deadlines, and completed tasks.
   - Integrate with popular calendar applications (e.g., Google Calendar, Outlook) to sync task deadlines and reminders.
   - Include a messaging feature to enable team members to communicate directly within the task interface.
   - The system should generate reports on task completion rates, team performance, and project progress.
   - Comprehensive test cases should be provided to validate the following scenarios: creating a task, assigning a task, updating task status, deadline synchronization with calendars, and generating reports. Edge cases should include handling tasks with overlapping deadlines, tasks with no assigned users, and tasks with long descriptions.


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
First persist working projects, assignments, status history, dashboards, messaging, authentication, authorization, and a provisional calendar adapter. The harness then delivers a calendar-adapter dependency contract with stable provider identifiers, timezone conversion, retry idempotency, update/cancellation semantics, and conflict policy. Consume that exact receipt, revise only calendar integration artifacts, preserve all unaffected task behavior, and write solution.py plus a receipt-bound closure under /app/output_data.
