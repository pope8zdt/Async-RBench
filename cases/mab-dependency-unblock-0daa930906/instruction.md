Software Development Task:

Please write a web application called ArtCollab that facilitates collaborative digital art creation among multiple users. ArtCollab is a real-time, multi-user web application that allows artists to work together on a single canvas, providing a suite of tools for drawing, painting, and editing, with real-time synchronization of changes.
1. Implementation requirements:
   - Frontend: Develop a responsive web interface using HTML, CSS, and JavaScript (React.js preferred) that supports real-time collaboration. The interface should include tools for drawing, painting, and editing, such as brush tools, color pickers, and layer management. Implement real-time updates using WebSockets to ensure all users see changes as they are made.
   - Backend: Create a robust backend server using Node.js and Express.js that handles real-time communication between clients. Implement user authentication and session management to ensure secure access. The server should manage canvas state and synchronize changes across all connected clients. Use a database (such as MongoDB) to store user data, project files, and collaboration history.
   - Database: Design a database schema to store user accounts, project metadata, and collaboration sessions. Ensure that the database can efficiently handle real-time updates and support multiple concurrent users. Implement backup and recovery mechanisms to prevent data loss.
   - Security: Implement security measures to protect user data and prevent unauthorized access. Use secure protocols for communication (HTTPS, WSS) and store sensitive information (such as passwords) securely using encryption. Implement rate limiting and input validation to prevent common web vulnerabilities.
   - Performance: Optimize the application to handle a large number of concurrent users and ensure low latency for real-time collaboration. Implement efficient data structures and algorithms to manage canvas state and updates. Use caching and load balancing techniques to improve performance and scalability.


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
Persist local drawing tools, layers, project history, authentication, and security checks while the synchronization specialist is a resource-constrained straggler. The harness then delivers the WebSocket operation protocol. Prioritize that critical path, bind acknowledgements and conflicts to revisions, preserve local canvas history, and reverify duplicate/concurrent operations.
