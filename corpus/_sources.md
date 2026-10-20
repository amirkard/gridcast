# Documents for retrieval

Put the documents for the agent's document search in this folder (.pdf, .md or
.txt). They are not committed: only this list is. Files whose names start with
"_" are skipped by the ingestion.

Suggested starting set:

1. ENTSO-E, *Load and Consumption Data: Definitions*:
   https://eepublicdownloads.entsoe.eu/clean-documents/pre2015/publications/ce/Load_and_Consumption_Data.pdf
2. Elia, *Load and load forecasts* (save the web page as PDF from the browser):
   https://elia.be/grid-data/load-and-load-forecasts

README.md and NOTES.md from the repository root are always included.

Then run:

    uv run python -m gridcast.ingest_docs
