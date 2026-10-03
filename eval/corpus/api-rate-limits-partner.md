# Partner API v2: Rate Limits

The partner API is a separate product from the public API. It serves resellers and integrators
under a signed partner agreement, and its limits are counted per partner token, not per API key.

## Limits

Each partner token may send 300 requests per minute, with short bursts of up to 50 requests per
second. Webhook deliveries from us to the partner do not count against the limit. Export
endpoints count as five requests each.

## Exceeding the limit

Requests over the limit receive HTTP status 429 with a Retry-After header. A partner whose
integration keeps sending requests after receiving 429 responses is blocked for 24 hours, and the
partner manager is notified.

## Monitoring

Responses carry the headers X-Partner-Quota-Limit and X-Partner-Quota-Used. The partner portal
shows the usage of the last thirty days per token.

## Raising the limits

A partner can ask the partner manager for a temporary quota increase of up to thirty days, for
example during a data migration. Permanent increases require an amendment to the partner
agreement.
