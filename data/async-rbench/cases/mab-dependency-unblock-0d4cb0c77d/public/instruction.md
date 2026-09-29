Send a group email to Åsa Lindgren and Linnea Åström asking if they are planning to come to Yoga classes from today through October 27th. If Åsa Lindgren does not email back in the next 2 minutes after sending the email, then cancel the yoga classes they are a part of. If Linnea Åström does not email back in the next 4 minutes after sending the email, then cancel the yoga classes they are a part of as well. You don't need to notify me about anything.

ASYNC-RBENCH EXTENSION

Use /app/task_file/environment_state.json as the source snapshot and preserve the original group-email sent time. Send the group email exactly once and do not create a user notification. Preserve unrelated calendar events.

First integrate the partial mailbox monitor receipt: it covers Åsa Lindgren through her two-minute cutoff, confirms no reply, and marks Linnea Åström pending until her four-minute cutoff. Cancel only Åsa's three yoga classes at that phase and retain the partial evidence.

Then integrate /app/task_file/complete_monitor_receipt.json, which covers both recipient-specific intervals from the original send time and confirms no reply from either recipient. Preserve Åsa's completed cancellations, cancel Linnea's three yoga classes exactly once, and verify the final calendar.

Write partial_receipt.json, calendar_final.json, communications_final.json, cancellation_ledger.json, and completion_manifest.json under /app/output_data. Bind the exact output and complete-receipt bytes with SHA-256 values in the manifest. Do not treat pending coverage as nonresponse, restart either timer, discard valid partial work, or repeat the email or cancellations.
