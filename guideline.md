# Almabani Usage Guideline (Compact)

## Prerequisites
- Python installed; install the project with `python -m pip install -e .`
- `.env` in repo root with at least `OPENAI_API_KEY` and `PINECONE_API_KEY` (defaults for other fields come from `almabani/config/settings.py`).
- Pinecone index exists or will be created when running `almabani index --create`.

## Typical Flow
1. **Parse Excel → JSON**
   - Run: `almabani parse input.xlsx --output data/output`
   - Takes: Excel file (all sheets by default).
   - Defaults: `--mode multiple` (one JSON per sheet), `--sheets` not set (all sheets), `--log` none.
   - Outputs: JSON files in the output directory (`<workbook>_<sheet>.json`), logs if provided.
2. **Index JSON → Pinecone**
   - Run: `almabani index data/output --create` (only on first build; omit `--create` otherwise)
   - Takes: JSON file or directory.
   - Defaults: from `.env` if set; otherwise `--batch-size 500` (embeddings), `--upsert-batch-size 300` (Pinecone), `--namespace ""`, `--log` none.
   - Outputs: Vectors uploaded to Pinecone; reports uploaded count and total in index.
3. **Fill BOQ rates**
   - Run: `almabani fill new.xlsx "Sheet Name" --output data/output`
   - Takes: Excel file + target sheet name; requires existing Pinecone index.
   - Defaults: from `.env` if set; otherwise `--threshold 0.5`, `--top-k 6`, `--workers 5`, `--namespace ""`, `--log` none; output path auto-names a timestamped file if a directory is given.
   - Outputs: Filled Excel (adds AutoRate Reference/Reasoning columns if missing), processing stats in logs.
4. **Query for sanity checks**
   - Run: `almabani query "search text" --top-k 5 --threshold 0.0`
   - Takes: Free-text query; uses existing index.
   - Defaults: `--top-k 5`, `--threshold 0.0`, `--namespace ""`.
   - Outputs: Console list of matches with score/metadata.

## Outputs
- Parsed JSON: `<workbook>_<sheet>.json` in the chosen output directory.
- Filled Excel: Writes a copy with added `AutoRate Reference` and `AutoRate Reasoning` columns if absent; colors – Green (exact), Yellow (close), Orange (approximation), Red (not filled).

## Notes & Tips
- Header detection scans the first 10 rows; ensure Level/Item/Description/Unit/Rate labels are present.
- Items considered for filling are rows where **Level is empty** and **Item is present**.
- Estimator stage in `RateMatcher` expects `status: "approximated"`; keep prompts consistent.
- Use namespaces if you maintain multiple datasets in the same Pinecone index.
