# Google Sheet headers for the samples

Create one Google Sheet and add these tabs, with the header row exactly as written (row 1).

**Leads** (01 · AI Lead Qualifier)
leadId | receivedAt | name | email | company | website | role | budget | timeline | source | score | tier | intent | summary | fitReasons | redFlags | nextStep | aiStatus | message

**Tickets** (02 · AI Support Email Triage)
receivedAt | from | subject | category | priority | sentiment | summary | needsHuman | draftSaved | aiStatus | threadId

**Vendors** (03 · AI Invoice Processor, read by the agent)
vendorName | taxId | approved | defaultCurrency

**Invoices** (03 · AI Invoice Processor)
processedAt | source | fileName | vendorName | vendorApproved | invoiceNumber | invoiceDate | dueDate | currency | subtotal | tax | total | lineItemCount | lineItems | status | anomalies | confidence
