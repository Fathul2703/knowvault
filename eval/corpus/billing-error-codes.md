# Billing Service Error Codes

The billing service charges customers' saved payment methods at the start of each billing
period. When a charge fails, the service records one of the error codes below on the invoice and
shows a short explanation in the customer portal.

## ERR_4713

ERR_4713 means the card was declined by the issuing bank. The bank does not tell us why. The
service retries the charge after 24 hours and again after 72 hours; after the second retry the
customer receives an email asking them to update their card.

## ERR_4171

ERR_4171 means the currency of the invoice does not match the currency of the payment method.
This happens when a customer changes their billing country. Support must ask the customer to add
a payment method in the invoice currency; retrying the charge never helps.

## ERR_7411

ERR_7411 means the tax rate for the customer's region is missing, so the invoice total cannot be
calculated. The invoice stays in draft until the finance team adds the rate in the tax table.
Customers are not charged while an invoice has this error.

## Reporting

A daily report lists every invoice with an error code. Finance reviews the report each morning
and escalates any code that affects more than twenty invoices in one day.
