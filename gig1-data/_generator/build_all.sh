#!/usr/bin/env bash
# Rebuild all Gig 1 portfolio samples (before + after) and QA them.
# Run from anywhere:  bash portfolio/gig1-data/_generator/build_all.sh
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"
DK="$ROOT/../../tools/gig1-data/datakit_cli.py"

python "$HERE/make_samples.py"
python "$HERE/make_pdf.py"

cd "$ROOT/01-customer-list"
python "$DK" clean --config job_customers.json -o after_customers_clean.xlsx
python "$DK" qa after_customers_clean.xlsx

cd "$ROOT/02-pdf-statement-invoices"
python "$DK" pdf before_statement_and_invoices.pdf -o after_extracted_reconciled.xlsx
python "$DK" qa after_extracted_reconciled.xlsx

cd "$ROOT/03-sales-merge"
python "$DK" clean --config job_sales_merge.json -o after_sales_merged_summary.xlsx
python "$DK" qa after_sales_merged_summary.xlsx
echo "all samples rebuilt"
