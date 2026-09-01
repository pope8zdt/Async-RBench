Software Development Task:

Please write a program called Music_Collaborator that facilitates collaborative music composition among multiple users. Music_Collaborator is a web-based application that enables musicians to work together in real-time to create and refine musical compositions. The application supports the integration of various musical elements, such as melodies, harmonies, and lyrics, and provides tools for users to collaborate effectively, even if they are in different locations.
1. Implementation requirements:
   - The application should allow multiple users to log in and collaborate on the same musical project in real-time.
   - Users should be able to input musical notes, melodies, and harmonies using a graphical interface or by uploading MIDI files.
   - The application should include a feature for real-time audio playback, allowing users to hear the composition as it evolves.
   - Users should be able to add, edit, and delete lyrics, and the application should provide basic sentiment analysis and thematic insights for the lyrics.
   - The application should support version control, allowing users to save and revert to previous versions of the composition.
   - The system should adapt to user feedback by suggesting musical adjustments based on the current composition, such as recommending harmonies or suggesting melody variations.
   - The application should provide a chat feature for users to communicate and coordinate their efforts while working on the composition.
   - The application should be scalable and able to handle multiple simultaneous users and projects without performance degradation.


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
Persist collaboration, lyric, chat, and revision work before the MIDI playback contract is complete. The harness then delivers the completed MIDI/timing result. Integrate only the affected playback and serialization paths, preserve the existing collaboration state, and close with receipt-bound re-verification.
