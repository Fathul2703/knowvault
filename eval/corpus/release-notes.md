# Release Notes: Ledger App 2.3 and 2.4

## Version 2.4.0

Version 2.4.0 adds multi-currency invoices. An invoice can now mix line items in different
currencies; totals are converted with the exchange rate of the invoice date. The export to
spreadsheet now keeps the original currency in a separate column.

Fixed in 2.4.0: rounding errors of one cent on invoices with more than fifty lines, and a crash
when a customer name contained an emoji.

Version 2.4.0 removes the legacy CSV importer. Customers who still upload CSV files must switch
to the new import wizard, which validates the file before anything is saved.

## Version 2.3.2

Version 2.3.2 is a security release. It closes a flaw that allowed a user with read-only access
to download attachments of invoices they could not otherwise see. All customers should update.

## Version 2.3.0

Version 2.3.0 introduced recurring invoices. A recurring invoice is created automatically every
month, quarter or year and can be paused at any time. Reminders for unpaid invoices are now sent
three days before and seven days after the due date.
