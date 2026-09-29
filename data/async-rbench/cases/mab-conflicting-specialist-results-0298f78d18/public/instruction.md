Create an event titled "Celebration" for Saturday of next week, one hour after my lunch break with Sunita for 4 hours. Please send a group invitation through email to the friends on my contacts that are the same age as me, and that all the expenses for the trip over will be paid by me. Let me know when all things have been done. 

If anyone declines the invitation, remove the people that declined from my contacts list and invite the people on my contacts that are one year older than me in a new group invitation email. After sending them the group invitation, let me know who has accepted, declined or who else have been invited if anyone declined.

ASYNC-RBENCH EXTENSION

The RSVP monitor delivers the same completed decline batch twice after the first delivery has already been applied.
Treat the second delivery as a replay. Use /app/task_file/task_state.json and /app/task_file/rsvp_replay.json
as the disclosed application state. Schedule the four-hour Celebration event, send the initial same-age group
invitation, remove both declining contacts, and send exactly one replacement group invitation to the one-year-older
cohort. Produce /app/output_data/schedule.json, initial_invitation.json, contacts_after.json,
replacement_invitation.json, status_report.json, replay_receipt.json, action_ledger.json, and
decision_manifest.json. The replay must not delete contacts twice, resend the replacement invitation, or duplicate
the final status. Bind every final artifact and disclosed input by exact SHA-256.
