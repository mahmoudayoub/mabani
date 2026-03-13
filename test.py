"""
Prompt-only BOQ price-code filler using OpenAI Responses API + Code Interpreter.

What this does:
1) Uploads your BOQ workbook and the 3 codebook workbooks to OpenAI Files.
2) Starts a Responses API call with Code Interpreter.
3) Attaches the uploaded files directly to the Code Interpreter container.
4) Instructs the model (via prompt only) to open the Excel files, match rows,
   fill the BOQ "Code" column, create a review log, and save a new .xlsx file.
5) Downloads the generated .xlsx from the container to your local machine.

Requirements:
    pip install --upgrade openai

Environment:
    export OPENAI_API_KEY="your_api_key_here"

Notes:
- This does NOT require you to write a matching script.
- The model will generate temporary Python inside the sandbox for this run.
- For large spreadsheets, this avoids relying on input_file spreadsheet augmentation.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


# =========================
# Configuration
# =========================

MODEL = "gpt-5.2"       # You can swap this later if you want
MEMORY_LIMIT = "4g"     # 1g, 4g, 16g, or 64g
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Your local source files
BOQ_PATH = Path("2-Terminal.xlsx")
CIVIL_PATH = Path("AI Codes - Civil.xlsx")
ELECTRICAL_PATH = Path("AI Codes Electrical.xlsx")
MECHANICAL_PATH = Path("AI Codes Mechanical.xlsx")

# Output filename you want the model to create
DESIRED_OUTPUT_FILENAME = "2-Terminal_with_pricecodes.xlsx"


# =========================
# Prompt
# =========================

SYSTEM_INSTRUCTIONS = """
You are an Excel-processing agent using the python tool.

You MUST use the python tool.
Open the uploaded Excel files directly in Python and process the full workbooks.

Your job:
- Use the BOQ workbook as the target workbook.
- Use the other uploaded workbooks as codebooks.
- Fill the BOQ 'Code' column with the most appropriate price code.

Rules:
1) Work on the full workbook, not a preview.
2) Identify the BOQ worksheet automatically if there is only one main BOQ sheet; otherwise prefer a sheet named similarly to '2-Terminal'.
3) For each BOQ row where the 'Code' cell is blank:
   - Use 'Description' as the primary matching field.
   - Use 'Trade', 'Unit', and 'Bill description' as supporting signals when available.
   - Prefer exact matches after normalization first.
   - Then use fuzzy text similarity if exact matching is not available.
   - If confidence is low, leave the Code blank.
4) Add a sheet named 'AI_Mapping_Log' if it does not already exist.
   For each processed BOQ row, log:
   - BOQ row number
   - chosen code (if any)
   - matched source workbook/sheet
   - confidence or score
   - status = FILLED / REVIEW / SKIPPED
5) Save exactly one final updated workbook as:
   2-Terminal_with_pricecodes.xlsx

Important:
- Preserve the original BOQ formatting and formulas as much as possible.
- Do not overwrite the original uploaded file in-place if that risks corruption; instead save a new workbook.
- If sheet/column names vary slightly, detect them robustly.
- Return a short summary of how many rows were filled, how many were flagged for review, and cite the generated .xlsx file.
""".strip()

TASK_PROMPT = """
Please process the uploaded BOQ workbook and the three uploaded codebook workbooks.

Files:
- 2-Terminal.xlsx  (target BOQ workbook)
- AI Codes - Civil.xlsx
- AI Codes Electrical.xlsx
- AI Codes Mechanical.xlsx

Target action:
Fill the BOQ 'Code' column with the correct price codes based on the uploaded codebooks.

Matching strategy:
- Primary key: BOQ 'Description'
- Secondary hints: 'Trade', 'Unit', 'Bill description'
- Try exact normalized matching first, then fuzzy matching
- If uncertain, leave blank and mark REVIEW in AI_Mapping_Log

Final output:
- Create exactly one updated workbook named:
  2-Terminal_with_pricecodes.xlsx
- Then provide a short completion summary.
""".strip()


# =========================
# Helpers
# =========================

def to_plain(obj: Any) -> Any:
    """
    Convert SDK objects / Pydantic models into plain Python dict/list/scalars,
    recursively, so we can parse response annotations safely.
    """
    if obj is None:
        return None

    # Pydantic-style objects in newer SDKs
    if hasattr(obj, "model_dump"):
        try:
            return to_plain(obj.model_dump())
        except TypeError:
            try:
                return to_plain(obj.model_dump(mode="python"))
            except Exception:
                pass

    if isinstance(obj, dict):
        return {k: to_plain(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]

    # Fallback for simple objects with __dict__
    if hasattr(obj, "__dict__"):
        return {
            k: to_plain(v)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }

    return obj


def upload_user_file(client: OpenAI, path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with path.open("rb") as f:
        uploaded = client.files.create(
            file=f,
            purpose="user_data",
        )
    return uploaded.id


def collect_container_file_citations(response_obj: Any) -> List[Dict[str, str]]:
    """
    Walk the full response payload and collect all container_file_citation annotations.
    Returns a list of dicts with: container_id, file_id, filename.
    """
    data = to_plain(response_obj)
    found: List[Dict[str, str]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            # Direct annotation object
            if node.get("type") == "container_file_citation":
                container_id = node.get("container_id")
                file_id = node.get("file_id")
                filename = node.get("filename") or "downloaded_file"
                if container_id and file_id:
                    found.append(
                        {
                            "container_id": container_id,
                            "file_id": file_id,
                            "filename": filename,
                        }
                    )
            for value in node.values():
                walk(value)

        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)

    # Deduplicate while preserving order
    unique: List[Dict[str, str]] = []
    seen: set[Tuple[str, str]] = set()

    for item in found:
        key = (item["container_id"], item["file_id"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def pick_output_xlsx(citations: List[Dict[str, str]]) -> Optional[Dict[str, str]]:
    """
    Prefer an .xlsx citation. If none exist, return the first citation if any.
    """
    for item in citations:
        if item["filename"].lower().endswith(".xlsx"):
            return item
    return citations[0] if citations else None


def download_container_file(
    client: OpenAI,
    container_id: str,
    file_id: str,
    out_path: Path,
) -> Path:
    content = client.containers.files.content.retrieve(
        container_id=container_id,
        file_id=file_id,
    )
    data = content.read()
    out_path.write_bytes(data)
    return out_path


# =========================
# Main
# =========================

def main() -> None:
    client = OpenAI()

    print("Uploading files...")
    boq_file_id = upload_user_file(client, BOQ_PATH)
    civil_file_id = upload_user_file(client, CIVIL_PATH)
    electrical_file_id = upload_user_file(client, ELECTRICAL_PATH)
    mechanical_file_id = upload_user_file(client, MECHANICAL_PATH)

    print("Uploaded:")
    print(f"  BOQ        : {boq_file_id}")
    print(f"  Civil      : {civil_file_id}")
    print(f"  Electrical : {electrical_file_id}")
    print(f"  Mechanical : {mechanical_file_id}")

    print("\nRunning prompt-only Code Interpreter job...")
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": "medium"},
        instructions=SYSTEM_INSTRUCTIONS,
        input=TASK_PROMPT,
        tools=[
            {
                "type": "code_interpreter",
                "container": {
                    "type": "auto",
                    "memory_limit": MEMORY_LIMIT,
                    "file_ids": [
                        boq_file_id,
                        civil_file_id,
                        electrical_file_id,
                        mechanical_file_id,
                    ],
                },
            }
        ],
        tool_choice="required",
    )

    # Print model summary text, if any
    print("\nModel summary:\n")
    print(getattr(response, "output_text", "") or "(No text summary returned)")

    # Find generated file citation(s)
    citations = collect_container_file_citations(response)
    if not citations:
        raise RuntimeError(
            "No generated file citation was found in the response. "
            "The model may not have produced an output file. "
            "Try rerunning, increasing memory, or strengthening the prompt."
        )

    chosen = pick_output_xlsx(citations)
    if not chosen:
        raise RuntimeError("No downloadable output file found.")

    # Use the desired local output path if the model produced an xlsx
    local_name = DESIRED_OUTPUT_FILENAME
    if not chosen["filename"].lower().endswith(".xlsx"):
        local_name = chosen["filename"]

    local_output_path = OUTPUT_DIR / local_name

    print("\nDownloading generated file...")
    download_container_file(
        client=client,
        container_id=chosen["container_id"],
        file_id=chosen["file_id"],
        out_path=local_output_path,
    )

    print(f"\nDone. Saved updated workbook to:\n  {local_output_path.resolve()}")


if __name__ == "__main__":
    main()
