Software Development Task:

Please write a system called PhotoCollabEditor that enables multiple users to collaboratively edit photos in real-time. PhotoCollabEditor is a web-based application that allows users to work together on editing photos, applying filters, adjusting colors, and removing backgrounds, with changes visible to all participants immediately.
1. Implementation requirements:
   - Frontend: Develop a responsive user interface using React or Vue.js that allows users to upload photos, select tools, and apply filters. The interface should support real-time collaboration, displaying changes made by all users simultaneously.
   - Backend: Implement a Node.js server using Express to handle real-time communication between users. Use WebSockets (via Socket.io) to enable instant updates and synchronize editing actions across multiple clients.
   - Database: Design a MongoDB database to store user sessions, photo metadata, and editing actions. Ensure that the database can handle concurrent writes and reads efficiently to support real-time collaboration.
   - Collaboration Features: Implement features for user authentication and session management. Allow users to create and join editing sessions, where they can see who is currently working on the photo and chat with other participants.
   - Editing Tools: Provide a comprehensive set of tools for photo editing, including filters, color adjustments, and background removal. Use machine learning algorithms to enhance the accuracy and speed of background removal and color palette generation.
   - Performance: Optimize the system to handle large images and multiple users without significant lag. Implement caching and efficient data transfer protocols to minimize latency.
   - Security: Ensure that the system is secure by implementing proper authentication, authorization, and data encryption. Protect user data and prevent unauthorized access to editing sessions.


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

ASYNC-RBENCH EXTENSION
During the task, the harness may deliver independently produced evidence. Treat a delivered receipt as new evidence rather than as an answer. Reassess only the work actually affected by that evidence, preserve still-valid work, and verify the final task outcome. Runtime event details are intentionally not disclosed in advance.
