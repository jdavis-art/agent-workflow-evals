You are running the seed-drift check of a weekly operations review. In the folder {fixtures} read
factory-operations.md (the Line Loading table is the source of truth), the project files under projects/,
and seed-data.json (a dashboard seed). Compare the seed against the table and project files. Report drift:
projects missing from the seed, box counts that differ, $/box that differ from the contract value, statuses
that differ. Name every drifted project explicitly with what differs. If drift exists, end with a
ready-to-paste build-session prompt that says exactly which fields in seed-data.json to change and to what.
If there is no drift, say exactly: Seed matches vault.
