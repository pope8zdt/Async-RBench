Software Development Task:

Please write a system called SportsTeamCollaborator that facilitates the collaborative analysis of sports match data among multiple agents (coaches, analysts, and players). SportsTeamCollaborator is a web-based platform that allows users to upload and analyze sports match data, track player performance, and share insights in real-time. The system supports the creation of detailed reports, performance metrics, and interactive visualizations, and it enables multiple users to collaborate on the analysis and provide feedback.
1. Implementation requirements:
   - The system should allow users to upload various types of sports match data, including video files, CSV files with performance metrics, and live data streams.
   - Implement a user role system with different permissions for coaches, analysts, and players. Coaches should have full access to all features, analysts should be able to perform data analysis and share reports, and players should be able to view their performance metrics and receive feedback.
   - The system should provide real-time collaboration features, such as shared notes, comments, and chat functionality, to facilitate communication among users during the analysis process.
   - Develop a comprehensive suite of test cases to validate the system's functionality, including: 
- Uploading different file types and data formats 
- User role management and permission verification 
- Real-time collaboration features (e.g., shared notes, comments, and chat) 
- Performance metric calculations and report generation 
- Handling edge cases such as large file uploads, concurrent user edits, and network disruptions
   - Ensure the system can handle large datasets efficiently and provide real-time updates without significant latency.
   - The system should be scalable to support multiple teams and a large number of users, and it should include robust security measures to protect user data and privacy.


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
First persist team-isolated match uploads, normalized player metrics, role permissions, and accepted collaboration sequence 42. The harness then delivers a concurrent analyst edit carrying expected sequence 41. Consume that exact receipt, classify and reject the superseded edit without changing accepted notes, comments, chat, metrics, or reports, preserve team isolation and permissions, and write solution.py plus a receipt-bound closure under /app/output_data.
