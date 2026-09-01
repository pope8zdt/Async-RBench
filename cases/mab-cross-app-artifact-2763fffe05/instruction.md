Software Development Task:

Please write a software application called BookSynergy that facilitates the creation and management of collaborative reference book projects. BookSynergy is a web-based platform that allows multiple users to contribute to the creation of comprehensive reference books, including writing, editing, and reviewing content, as well as managing the publication process.
1. Implementation requirements:
   - Frontend: Develop a responsive and user-friendly interface that supports user authentication, project creation, content editing, and version control. The interface should include features such as real-time collaboration, markdown support for text formatting, and a WYSIWYG editor for non-technical users.
   - Backend: Implement a robust backend service that handles user data, project management, and content storage. The backend should support RESTful APIs for frontend interactions, secure user authentication, and authorization, and provide version control for the collaborative content.
   - Database: Design a database schema to efficiently store user profiles, project metadata, content revisions, and collaboration logs. The database should support scalable storage and fast retrieval of data, with mechanisms to prevent data loss and ensure data integrity.
   - Integration: Ensure seamless interaction between the frontend and backend services, including real-time updates for collaborative editing, secure data transmission, and efficient handling of large files. The system should also support integration with external services for content review, such as GitHub for version control or third-party proofreading tools.


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
First persist authentication, project membership, editor behavior, realtime subscribers, external review hooks, and provisional content objects. The harness then delivers the authoritative BookSynergy schema for books, sections, immutable parented revisions, reviews, contributor roles, and publication transitions. Consume that exact receipt, replace provisional revision assumptions, reject stale parents, preserve unaffected membership and integration behavior, and write solution.py plus a receipt-bound closure under /app/output_data.
