# Public API Rate Limits

The public API limits how many requests a client can send so that one integration cannot slow
down everyone else. Limits are counted per API key.

## Default limits

The free plan allows 60 requests per minute and 10,000 requests per day. The business plan
allows 600 requests per minute and has no daily cap. Bulk endpoints count as ten requests each,
because they do the work of many single calls.

## When a limit is reached

The API answers with HTTP status 429 and a Retry-After header that says how many seconds to
wait. Clients should wait at least that long and then retry with exponential backoff and random
jitter. Clients that ignore Retry-After and keep sending requests are blocked for one hour.

## Headers

Every response carries three headers: X-RateLimit-Limit, X-RateLimit-Remaining and
X-RateLimit-Reset. The reset value is a Unix timestamp. Use the remaining count to slow down
before the limit is hit instead of reacting to errors.

## Higher limits

Customers who need more can request a temporary increase for a migration or a launch. The
request goes through the account manager and must state the expected traffic and the dates.
Temporary increases last at most fourteen days.
