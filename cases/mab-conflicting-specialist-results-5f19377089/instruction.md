This database is used for managing financial data within a Finance Management System. It tracks users, their accounts, transactions, investments, and investment transactions.
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
First persist a provisional comparison of all five declared root-cause hypotheses. An independent authority worker then returns a receipt bound to the host-owned PostgreSQL checkpoint. Reopen the diagnosis, preserve the valid comparison, adopt the authoritative receipt, and close with exactly VACUUM as the selected maintenance cause. Write the final receipt-bound closure under /app/output_data.

The source text describes a database, but this isolated participant container does not expose a live localhost PostgreSQL service; the independent authority workstream carries the evaluator-owned checkpoint probe. After accepting that result, promote its `/app/output_data/event_receipt.json` into the main workspace. Run `/app/task_file/scripts/write_database_diagnosis.py` to create `database_diagnosis.json`, then run `/app/task_file/scripts/write_manifest.py` to create `decision_manifest.json`. Preserve `provisional_checkpoint.json` and `preserved_source_facts.json`. Commit `authority_receipt`, `database_diagnosis`, and `final_state` with `final=true` and lineage containing the accepted authority completion, then reverify before declaring completion.
