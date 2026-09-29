In `/app/logs` there are multiple `.log` files from different services. Your task is to scan all `.log` files and count how many lines contain "ERROR", "WARNING", and "INFO".
  
Output your results to `/app/summary.csv` with the following structure:
severity,count
ERROR,<total number of ERROR lines across all files>
WARNING,<total number of WARNING lines across all files>
INFO,<total number of INFO lines across all files>

The output should be a valid CSV file with exactly four lines in total (one header line and one line for each severity level).

ASYNC-RBENCH EXTENSION
The service logs are independent shards of this same aggregate. Preserve the supplied log files. In addition to summary.csv, save /app/aggregation.json as an object with a contributions array containing exactly one object for each original log file. Each contribution has source_file (basename), source_sha256 (SHA-256 of the log bytes), and counts (the ERROR, WARNING, and INFO line counts). The CSV totals must equal the sum of those per-file contributions. Save the corresponding per-file JSON reports at /app/shards/<source_file>.json, with the same three fields. Report ordering and CSV severity ordering do not matter.

Independent counting workstreams are available for each source log; /app/count_shard.py can compute their report format from the source bytes. Transport notifications identify completed work; the reporting population is the original log files in /app/logs.
