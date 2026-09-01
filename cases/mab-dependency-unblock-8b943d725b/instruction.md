This database is used for a Social Media platform, where users can create posts, comment on posts, like posts, follow other users, send direct messages, and upload media. The schema covers key aspects such as user information, social interactions (like, comments, follow), messaging, and media management.
Recently, during operation, the database has seen performance issues. Use sql queries to find out what is wrong, and find out the reason that caused it. The root cause can be only two of the following: 'INSERT_LARGE_DATA', 'MISSING_INDEXES', 'LOCK_CONTENTION', 'VACUUM', 'REDUNDANT_INDEX', 'FETCH_LARGE_DATA', 'POOR_JOIN_PERFORMANCE,CPU_CONTENTION'. The planner should assign different agent to analyze possbility for each root cause and make final decision. Agents can also chat with each other to share information.  Please make the decision after using all these tools, as a premature decision may lead to incorrect conclusions.

Please make the decision after exploring all rootcauses, as a premature decision may lead to incorrect conclusions.
Please choose the most likely cause of the database anomaly from the following list, based on the expert agents: 
'INSERT_LARGE_DATA', 'LOCK_CONTENTION', 'VACUUM', 'REDUNDANT_INDEX', 'FETCH_LARGE_DATA'
You can ONLY CHOOSE two.
You have access to the Database, and you can perform queries to get the required information. Agents can also chat with each other to share information.
These tables include:
- `pg_stat_statements` (for detailed query stats)
- `pg_locks` (for lock waits and contention)
- `pg_stat_user_indexes` (for index usage)
- `pg_indexes` (for index definitions)
- `pg_stat_all_tables` (detailed statistics about vacuuming, auto vacuuming, and analyze operations for each table)
- `pg_stat_progress_vacuum` (for vacuum progress)
- `pg_stat_user_tables` (for dead tuples and vacuum stats)

ASYNC-RBENCH EXTENSION
Persist a provisional five-hypothesis diagnosis for the social media database, including still-valid findings about users, posts, comments, likes, followers, messages, and media. Do not finalize before the evaluator delivers a case-bound authority receipt after the database checkpoint. Verify the receipt identity and checkpoint digest, revise only the affected diagnosis, preserve valid prior findings, and write database_diagnosis.json plus the receipt-bound closure under /app/output_data. The selected and displaced causes are evaluator-owned and are not disclosed here.
