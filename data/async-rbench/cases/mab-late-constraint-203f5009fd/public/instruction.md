Software Development Task:

Please write a business software application called TeamSyncPro that facilitates seamless collaboration and project management across various departments within an organization. TeamSyncPro is a comprehensive project management system that integrates task management, resource allocation, and communication tools to enhance team productivity and project outcomes.
1. Implementation requirements:
   - The frontend should provide a user-friendly interface with features for task assignment, status updates, and real-time communication. It should support role-based access control to ensure that users can only view and interact with the information relevant to their roles.
   - The backend should handle the core functionalities such as task management, resource allocation, and performance tracking. It should support RESTful API endpoints for frontend interactions and should be capable of handling multiple concurrent users and large datasets.
   - The database should be designed to efficiently store and retrieve project data, including tasks, user profiles, and communication logs. It should support transactions and have mechanisms for data backup and recovery.
   - The system should support integration with third-party tools commonly used in business environments, such as calendar applications, email services, and CRM systems, to enhance its utility and flexibility.
   - The application should have a robust reporting module that can generate various types of reports, such as project progress reports, resource utilization reports, and performance metrics, to help managers make informed decisions.
   - The frontend and backend should communicate seamlessly through well-defined APIs, ensuring that data is synchronized in real-time and that the user experience is smooth and responsive.


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
Implement the requested project-management system while three upstream workstreams preserve tasks, resources, communication logs, and reporting state. The harness then completes an evaluator-owned RBAC/API dependency. Reconcile backend validation and frontend visibility with that contract, reject cross-department or altered-field requests, preserve valid state, and reverify closure.
