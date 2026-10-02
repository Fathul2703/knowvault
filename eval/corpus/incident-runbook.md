# Incident Runbook: Importer Service

This runbook covers the nightly importer that loads partner invoices into the ledger. It is
owned by the Platform team. The on-call engineer follows these steps before escalating.

## Error codes

The importer writes a single error code to the job log when it stops.

ERR_4711 means the connection to the storage cluster timed out. The importer retries three
times with a pause of 90 seconds between attempts before it gives up. When you see ERR_4711,
first check the status page of the storage cluster; most incidents clear on their own within
fifteen minutes.

ERR_4712 means the storage quota for the tenant is full. Retrying does not help. Ask the tenant
owner to archive old invoice batches, or raise the quota in the admin console after approval
from the finance lead.

ERR_5020 means a partner sent a file with an unknown column layout. Move the file to the
quarantine folder and notify the partner manager; never edit partner files by hand.

## Restarting the importer

Restart the importer only after the cause is understood. Use the deploy tool with the
command `deploy restart importer --region primary`. A restart replays the last unfinished batch,
so duplicate rows are not created. Do not restart more than twice in one hour; repeated
restarts hide the real cause.

## Escalation

Escalate to the Platform team lead when an incident lasts longer than 45 minutes or affects
more than one region. During weekends the escalation goes to the secondary on-call through the
paging system. Every incident that pages a human gets a short written review within five
working days, focused on what to change rather than who to blame.

## Dashboards

The importer dashboard shows batch duration, rows per second and the error rate per partner.
A batch normally finishes in under twelve minutes. Batches that take longer than thirty minutes
usually point to a slow partner endpoint rather than a problem in the importer itself.
