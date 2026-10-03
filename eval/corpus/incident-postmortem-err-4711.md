# Postmortem: Importer Outage of 14 March

Summary of the incident in which the nightly importer failed for every tenant. Written for the
engineering and support teams; it does not replace the runbook.

## What happened

At 01:10 the importer started to stop with ERR_4711 for all tenants at once. Retries did not
help, and the on-call engineer was paged after the third failed batch. Imports were restored at
03:50, so the outage lasted two hours and forty minutes. No data was lost; the failed batches were
imported again the next morning.

## Root cause

The storage cluster rejected new connections because of an expired TLS certificate on its load
balancer. The importer reported this as a connection timeout, ERR_4711, which hid the real cause.
The certificate had been renewed by hand the year before and was not in the renewal automation.

## What went well

The runbook's first step, checking the storage cluster's status page, quickly showed that the
cluster was unhealthy. Support informed the affected tenants within thirty minutes.

## Action items

- Add the load balancer certificate to the renewal automation.
- Send certificate expiry alerts thirty days in advance for every certificate in production.
- Make the importer log the TLS error instead of reporting a generic timeout.
