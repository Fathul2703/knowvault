# Data Retention Policy

This policy says how long the company keeps each kind of data and how it is deleted. It applies
to production systems, backups and exports. The privacy officer reviews it every year.

## Retention periods

Customer invoices are kept for ten years, because tax law requires it. Support conversations
are kept for two years after the ticket is closed. Application logs that may contain personal
data are kept for thirty days and then deleted automatically. Access logs of the admin console
are kept for one year for security investigations.

## Backups

Nightly database backups are kept for 35 days. Monthly backups are kept for one year and are
stored in a second region. Backups are encrypted with keys that are rotated every 90 days.
Deleting a record in production does not remove it from existing backups; it disappears when
the last backup containing it expires.

## Deletion requests

When a customer asks to delete their personal data, the request must be completed within 30
days. The support team confirms the identity of the requester before anything is deleted.
Invoices are exempt from deletion requests while the legal retention period runs, but their
personal fields are hidden from internal tools.

## Exports

Data exports for analysis must remove names, email addresses and phone numbers. An export may
only be kept for 90 days; after that the analyst deletes it and records the deletion in the
data catalogue.
