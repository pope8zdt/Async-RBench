Software Development Task:

Please write a collaborative system called CodeSquad that facilitates real-time code review and debugging among multiple developers. CodeSquad is a web-based application that enables developers to share code snippets, review each other's code, and collaboratively debug issues. It supports real-time communication, code annotation, and version control integration.
1. Implementation requirements:
   - Implement real-time code sharing and annotation features, allowing multiple developers to simultaneously view and comment on code snippets.
   - Integrate with popular version control systems (e.g., Git) to pull and push code changes, and to track the history of code reviews and debugging sessions.
   - Provide a chat interface for real-time communication and collaboration among developers, including the ability to send code snippets and error logs directly within the chat.
   - Support adaptive task management, where the system can dynamically adjust to different stages of the code review and debugging process, such as marking issues as resolved, re-opening them based on feedback, or escalating them to higher levels of review.
   - Include a dashboard that provides an overview of ongoing code reviews, debugging sessions, and the status of each task, with filters to sort and search for specific issues.
   - Ensure the system is scalable and can handle multiple concurrent sessions, with user authentication and role-based access control to manage permissions and data privacy.


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
First persist working snippets, annotations, chat, issue transitions, review comments, authentication, role permissions, and provisional repository references. The harness then delivers a Git-adapter dependency contract for repositories, branches, commits, diffs, review sessions, non-fast-forward handling, history reconstruction, retries, and idempotent pushes. Consume that exact receipt, revise only repository-bound review and history artifacts, preserve unaffected collaboration behavior, and write solution.py plus a receipt-bound closure under /app/output_data.
