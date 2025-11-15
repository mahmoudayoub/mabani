# Excel to JSON Pipeline# Excel to JSON Pipeline# Excel to JSON Pipeline# Excel to JSON Pipeline



Convert Excel BOQ (Bill of Quantities) files into structured JSON format with hierarchical organization.



## OverviewConvert Excel BOQ (Bill of Quantities) files into structured JSON format with hierarchical organization.



This pipeline processes Excel files containing construction BOQ data and converts them into structured JSON format. It intelligently handles hierarchical levels (numeric levels 1, 2, 3, etc.) and consecutive c-level subcategories to create a clean, navigable data structure.



## Features## OverviewConvert Excel BOQ files to structured JSON format with hierarchical organization.A production-level, modular pipeline for converting Excel files with hierarchical BOQ (Bill of Quantities) data into JSON format.



- ✅ **Hierarchical Processing**: Builds tree structure from numeric levels (PART 1, PART 2, etc.)

- ✅ **C-Level Logic**: Handles consecutive c-level subcategories with proper parent-child relationships

- ✅ **Multi-Sheet Support**: Process single sheets or all sheets in a workbookThis pipeline processes Excel files containing construction BOQ data and converts them into structured JSON format. It intelligently handles hierarchical levels (numeric levels 1, 2, 3, etc.) and consecutive c-level subcategories to create a clean, navigable data structure.

- ✅ **Type Safety**: Pydantic models ensure data validation

- ✅ **Flexible Configuration**: YAML-based configuration for customization

- ✅ **Comprehensive Logging**: Detailed logs for debugging and monitoring

- ✅ **No API Dependencies**: Pure Python processing, no external API calls needed## Features## Overview## Table of Contents



## Directory Structure



```- ✅ **Hierarchical Processing**: Builds tree structure from numeric levels (PART 1, PART 2, etc.)- [Features](#features)

excel_to_json_pipeline/

├── src/- ✅ **C-Level Logic**: Handles consecutive c-level subcategories with proper parent-child relationships

│   ├── excel_parser.py          # Read Excel files and extract data

│   ├── hierarchy_processor.py   # Build hierarchical structure from levels- ✅ **Multi-Sheet Support**: Process single sheets or all sheets in a workbookThis pipeline processes Excel files containing Bill of Quantities (BOQ) data and converts them into structured JSON format. It preserves the hierarchical structure (levels 1, 2, 3) while flattening level "c" entries.- [Key Improvements](#key-improvements)

│   ├── json_exporter.py         # Export to JSON format

│   ├── models.py                # Pydantic data models- ✅ **Type Safety**: Pydantic models ensure data validation

│   └── pipeline.py              # Main orchestration logic

├── config/- ✅ **Flexible Configuration**: YAML-based configuration for customization- [Quick Start](#quick-start)

│   └── settings.yaml            # Configuration settings

├── input/                       # Place Excel files here- ✅ **Comprehensive Logging**: Detailed logs for debugging and monitoring

├── output/                      # Generated JSON files (one per sheet)

├── logs/                        # Processing logs with timestamps## Features- [Installation](#installation)

├── process_separate_sheets.py  # Main entry point

└── requirements.txt             # Dependencies## Directory Structure

```

- [Project Structure](#project-structure)

## Installation

```

```bash

# From project rootexcel_to_json_pipeline/- ✅ Process multiple sheets from Excel files- [Usage](#usage)

pip install -r excel_to_json_pipeline/requirements.txt

```├── src/



## Configuration│   ├── excel_parser.py          # Read Excel files- ✅ Hierarchical organization (Level 1 → Level 2 → Level 3)- [Hierarchy Logic](#hierarchy-logic)



The pipeline doesn't require API keys. All configuration is in `config/settings.yaml`:│   ├── hierarchy_processor.py   # Build hierarchical structure



```yaml│   ├── json_exporter.py         # Export to JSON- ✅ Automatic level "c" flattening- [Configuration](#configuration)

# Excel file settings

excel:│   ├── models.py                # Data models (Pydantic)

  header_row: 0  # Row index for headers (0-based)

  │   └── pipeline.py              # Main orchestration- ✅ Separate JSON file per sheet- [Output Format](#output-format)

# Output settings

output:├── config/

  indent: 2  # JSON indentation

  ensure_ascii: false  # Allow non-ASCII characters│   └── settings.yaml            # Configuration- ✅ Preserves item codes, descriptions, units, and rates- [Logging](#logging)

```

├── input/                       # Place Excel files here

## Usage

├── output/                      # Generated JSON files- [Examples](#examples)

### Process All Sheets

├── logs/                        # Processing logs

```bash

# Place Excel file in input/ folder├── process_separate_sheets.py   # Main entry point## Directory Structure- [Performance & File Sizes](#performance--file-sizes)

cp "your_file.xlsx" excel_to_json_pipeline/input/

└── requirements.txt             # Dependencies

# Run pipeline (processes all sheets)

cd excel_to_json_pipeline```- [Troubleshooting](#troubleshooting)

python process_separate_sheets.py



# Output: One JSON file per sheet in output/

# - Book1_Sheet1.json## Installation```- [Next Steps: Vector Store Preparation](#next-steps-vector-store-preparation)

# - Book1_Sheet2.json

# - etc.

```

```bashexcel_to_json_pipeline/- [Development](#development)

### Process Specific Sheet

# From project root

```bash

# Edit process_separate_sheets.py to specify sheet namepip install -r requirements.txt├── src/                      # Core modules- [Version History](#version-history)

python process_separate_sheets.py --sheet "Sheet Name"

``````



## How It Works│   ├── excel_parser.py       # Excel file reading



### 1. Excel Parsing## Usage



The pipeline reads Excel files and identifies:│   ├── hierarchy_processor.py # Hierarchy management---

- **Header row**: Typically contains "Level", "Item", "Description", "Unit", "Pricing"

- **Data rows**: All rows below header### Process All Sheets (Default)

- **Hierarchy markers**: "Level" column with numeric values (1, 2, 3) or "c"

│   ├── json_exporter.py      # JSON output

### 2. Hierarchy Building

```bash

**Level Structure:**

- **Level 1**: Top-level categories (e.g., "PART 1 - EARTHWORKS")# Place Excel file in input/ folder│   ├── models.py             # Data models## Features

- **Level 2**: Subcategories (e.g., "General Excavation")

- **Level 3**: Detail level (e.g., "Excavation for foundations")cp "your_file.xlsx" excel_to_json_pipeline/input/

- **Level c**: Special consecutive levels handled with custom logic

│   └── pipeline.py           # Main pipeline

**C-Level Logic:**

# Run pipeline

When consecutive c-levels appear:

1. First c followed by second c → Clear stack, add first to current parentcd excel_to_json_pipeline├── config/✨ **Modular Architecture**: Separate modules for parsing, processing, and exporting  

2. Second c followed by items → Add second c to stack

3. Items get: grandparent=first_c, parent=second_cpython process_separate_sheets.py



Example:```│   └── settings.yaml         # Configuration📊 **Hierarchical Processing**: Builds tree structure from numeric levels  

```

Level 2: General Excavation

  c: General Excavation: material excavated to be...

  c: Apron area### Process Specific Sheet├── input/                    # Place Excel files here🎯 **Simplified Structure**: Ignores 'c' subcategory levels for cleaner output  

    Item: 3.1.02 | Depth not exceeding 0.25m



Result for item 3.1.02:

- Grandparent: "General Excavation: material excavated to be..."Edit `config/settings.yaml`:├── output/                   # Generated JSON files🔒 **Type Safety**: Uses Pydantic models for data validation  

- Parent: "Apron area"

- Description: "Depth not exceeding 0.25m"```yaml

```

input_file: "your_file.xlsx"├── logs/                     # Log files⚙️ **Flexible Configuration**: YAML-based configuration for easy customization  

### 3. JSON Export

sheet_name: "Terminal"  # or null for all sheets

Each sheet is exported as a separate JSON file with structure:

```├── process_separate_sheets.py # Main script📝 **Comprehensive Logging**: Detailed logging for debugging and monitoring  

```json

{

  "sheet_name": "Terminal",

  "hierarchy": [Then run:├── requirements.txt          # Dependencies📦 **Batch Processing**: Process single files or entire directories  

    {

      "level": 1,```bash

      "description": "PART 1 - EARTHWORKS",

      "children": [python process_separate_sheets.py└── README.md                 # This file📁 **Multiple Output Modes**: Separate JSON file per sheet (default) or single combined file  

        {

          "level": 2,```

          "description": "General Excavation",

          "children": [```

            {

              "level": "c",## Configuration

              "description": "General Excavation: material...",

              "children": [## Key Improvements

                {

                  "level": "c",Edit `config/settings.yaml`:

                  "description": "Apron area",

                  "items": [## Installation

                    {

                      "item_code": "3.1.02",```yaml

                      "description": "Depth not exceeding 0.25m",

                      "unit": "m³",# Input/Output**91% File Size Reduction**: By ignoring 'c' subcategory levels, output files are dramatically smaller (173 MB → 16 MB)

                      "rate": 45.50,

                      "parent": "Apron area",input_directory: "input"

                      "grandparent": "General Excavation: material..."

                    }output_directory: "output"```bash

                  ]

                }log_directory: "logs"

              ]

            }# Install dependencies**Simpler Hierarchy**: Items placed directly under numeric levels instead of nested under 'c' subcategories

          ]

        }# Processing

      ]

    }input_file: "your_file.xlsx"        # Requiredpip install -r requirements.txt

  ]

}sheet_name: null                     # null = all sheets

```

output_mode: "separate"              # "separate" or "combined"```**Separate Files by Default**: Each sheet exports as individual JSON file for easier management

## Output Format



Each JSON file contains:

# Column Mapping (customize if your Excel has different columns)

### Item Fields

- **item_code**: Item reference number (e.g., "3.1.02")columns:

- **description**: Item description text

- **unit**: Unit of measurement (m³, m², nr, etc.)  level: "Unnamed: 0"## Usage## Quick Start

- **rate**: Unit rate/price (numeric)

- **parent**: Immediate parent description (from last c-level)  item: "Unnamed: 1"

- **grandparent**: Second-level parent description (from first c-level)

  description: "Unnamed: 2"

### Hierarchy Fields

- **level**: Numeric (1, 2, 3) or "c"  unit: "Unnamed: 3"

- **description**: Level description text

- **children**: Nested sub-levels  pricing: "Pricing"1. **Place Excel files** in the `input/` directory**Fastest way to get started:**

- **items**: Array of items at this level

```

## Logging



Logs are saved to `logs/excel_to_json_{timestamp}.log` with:

- Processing start/end times## Hierarchy Logic

- Sheets processed

- Items extracted per sheet2. **Run the pipeline:**```bash

- Hierarchy structure validation

- Any errors or warnings### Consecutive C-Levels



Example log output:   ```bash# 1. Place your Excel file in the input directory

```

2025-11-14 20:30:00 - INFO - Starting Excel to JSON pipelineWhen multiple c-levels appear consecutively, the pipeline creates parent-child relationships:

2025-11-14 20:30:01 - INFO - Processing file: Book_1.xlsx

2025-11-14 20:30:01 - INFO - Found 3 sheets   cd excel_to_json_pipelinecp "your_file.xlsx" input/

2025-11-14 20:30:02 - INFO - Sheet 'Terminal': Extracted 450 items

2025-11-14 20:30:03 - INFO - Exported: output/Book_1_Terminal.json**Example Excel Structure:**

2025-11-14 20:30:05 - INFO - Pipeline complete. Processed 3 sheets, 1,250 total items

``````   python process_separate_sheets.py



## ExamplesLevel | Item    | Description



### Input Excel Structure------|---------|---------------------------   ```# 2. Run the pipeline (using convenience script)



| Level | Item   | Description                        | Unit | Pricing |3     |         | PART 3 - EARTHWORKS

|-------|--------|------------------------------------|------|---------|

| 1     |        | PART 1 - EARTHWORKS               |      |         |c     |         | 3.1 - General Excavation./run.sh

| 2     |        | General Excavation                 |      |         |

| c     |        | General Excavation: material...    |      |         |c     |         | General Excavation: topsoil

| c     |        | Apron area                         |      |         |

|       | 3.1.02 | Depth not exceeding 0.25m         | m³   | 45.50   |      | 3.1.01  | Depth not exceeding 0.25m3. **Output:** JSON files will be created in `output/` directory

|       | 3.1.03 | Depth 0.25m to 0.50m              | m³   | 52.00   |

c     |         | General Excavation: material...

### Output JSON (simplified)

c     |         | Apron area   - One JSON file per Excel sheet# Or using the process script directly

```json

{      | 3.1.02  | Depth not exceeding 0.25m

  "sheet_name": "Sheet1",

  "hierarchy": [```   - Format: `{original_filename}_{sheet_name}.json`python process_separate_sheets.py

    {

      "level": 1,

      "description": "PART 1 - EARTHWORKS",

      "children": [**Resulting Hierarchy:**```

        {

          "level": 2,```

          "description": "General Excavation",

          "children": [PART 3 - EARTHWORKS## Input Format

            {

              "level": "c",  └─ 3.1 - General Excavation

              "description": "General Excavation: material...",

              "children": [      ├─ General Excavation: topsoilThat's it! Check the `output/` directory for your JSON files (one per sheet).

                {

                  "level": "c",      │   └─ Item 3.1.01

                  "description": "Apron area",

                  "items": [      └─ General Excavation: material...Excel file should have these columns:

                    {

                      "item_code": "3.1.02",          └─ Apron area

                      "description": "Depth not exceeding 0.25m",

                      "unit": "m³",              └─ Item 3.1.02- **Level**: Hierarchy level (1, 2, 3, or c)---

                      "rate": 45.50,

                      "parent": "Apron area",```

                      "grandparent": "General Excavation: material..."

                    }- **Item**: Item code

                  ]

                }**Key Rules:**

              ]

            }1. When c-level is followed by another c-level → clear stack, add first c as parent- **Bill description**: Item description## Installation

          ]

        }2. When c-level is followed by items → add c to existing stack, items get proper grandparent/parent

      ]

    }3. Stack maintains: `[grandparent_c, parent_c]` for items- **Unit**: Unit of measurement

  ]

}

```

## Output Format- **Rate**: Unit rate```

## Performance



Typical processing times:

- **Small files** (< 500 items): < 5 secondsEach sheet produces a JSON file: `{filename}_{sheet_name}.json`excel_to_json_pipeline/

- **Medium files** (500-2000 items): 5-15 seconds

- **Large files** (2000+ items): 15-30 seconds



No API calls means processing is very fast and has no usage costs.```json## Output Format├── config/



## Troubleshooting{



### No items extracted?  "source_file": "your_file.xlsx",│   └── settings.yaml          # Configuration file

- Check that "Level" column contains "c" markers

- Verify header row is correctly identified  "sheet_name": "Terminal",

- Review logs for parsing errors

- Ensure Excel file has standard structure  "hierarchy": [```json├── src/



### Wrong hierarchy?    {

- Verify c-levels are in correct order

- Check for empty rows between c-levels (they're skipped)      "level": 3,{│   ├── __init__.py

- Review c-level logic in `hierarchy_processor.py`

- Check logs for hierarchy building steps      "description": "PART 3 - EARTHWORKS",



### Missing parent/grandparent?      "item_type": "numeric_level",  "source_file": "example.xlsx",│   ├── models.py              # Pydantic data models

- C-level logic requires at least 2 consecutive c-levels

- Single c-level items won't have grandparent      "row_number": 7,

- Check that c-levels appear before items

      "children": [  "source_sheet": "Sheet1",│   ├── excel_parser.py        # Excel file parsing

### Excel file not found?

- Ensure file is in `input/` directory        {

- Check file name and extension (.xlsx)

- Verify file is not corrupted          "level": "c",  "hierarchy": [│   ├── hierarchy_processor.py # Hierarchy building logic



### JSON export fails?          "description": "3.1 - General Excavation",

- Check disk space

- Verify write permissions on `output/` directory          "item_type": "subcategory",    {│   ├── json_exporter.py       # JSON export functionality

- Check for invalid characters in descriptions

          "row_number": 9,

## Next Steps

          "children": [...]      "level": 1,│   └── pipeline.py            # Main orchestrator

After converting Excel to JSON:

        }

1. **Verify output**: Check JSON files are correctly structured

2. **Review hierarchy**: Ensure parent/grandparent relationships are correct      ]      "code": "1",├── input/                     # Place input Excel files here

3. **Prepare for vector store**: Move JSON files to `json_to_vectorstore/input/`

4. **Generate embeddings**: Run `json_to_vectorstore` pipeline to create vector database    }



## Integration with Other Pipelines  ]      "description": "Main Category",├── output/                    # Generated JSON files



This pipeline is the **first step** in the BOQ processing workflow:}



``````      "children": [├── logs/                      # Log files

Excel Files

    ↓

[excel_to_json_pipeline]

    ↓## Logging        {├── requirements.txt           # Python dependencies

JSON Files (hierarchical structure)

    ↓

[json_to_vectorstore]

    ↓Logs are saved to `logs/pipeline_YYYYMMDD_HHMMSS.log`          "level": 2,└── README.md                  # This file

Pinecone Vector Database

    ↓

[rate_filler_pipeline]

    ↓**Log Levels:**          "code": "1.1",```

Filled Excel Files

```- `INFO`: Processing progress



The JSON output from this pipeline serves as input for:- `DEBUG`: Detailed hierarchy decisions          "description": "Sub Category",

- **json_to_vectorstore**: Generates embeddings and uploads to Pinecone

- **rate_filler_pipeline**: Uses vector search to find matching items- `WARNING`: Missing data or anomalies



## Development- `ERROR`: Processing failures          "children": [---



### Adding Custom Logic



To customize hierarchy processing:## Next Steps            {



1. **Modify level detection**: Edit `excel_parser.py`

2. **Change hierarchy rules**: Edit `hierarchy_processor.py`

3. **Adjust output format**: Edit `json_exporter.py`After generating JSON files, use them with **json_to_vectorstore** pipeline to create embeddings and upload to Pinecone.              "level": 3,## Installation

4. **Update data models**: Edit `models.py`



### Testing

```bash              "code": "1.1.1",

```bash

# Process test filecd ../json_to_vectorstore

cp test_data.xlsx input/

python process_separate_sheets.pypython process_json_to_vectorstore.py              "description": "Item Description",### Prerequisites



# Check output```

cat output/test_data_Sheet1.json | jq .

```              "unit": "m2",- Python 3.8 or higher



## Dependencies## Troubleshooting



Key libraries:              "rate": 100.50- pip package manager

- **pandas**: Excel file reading

- **openpyxl**: Excel file manipulation**No JSON files generated?**

- **pydantic**: Data validation

- **pyyaml**: Configuration management- Check `logs/` for error messages            }



No API dependencies or external services required.- Verify Excel file is in `input/` directory



---- Ensure Excel file has correct column structure          ]### Setup



**Version**: 2.0  

**Last Updated**: November 14, 2025  

**Status**: Production Ready**Wrong hierarchy?**        }


- Check numeric level values (1, 2, 3, etc.)

- Verify 'c' levels are properly marked      ]1. **Install Python dependencies:**

- Review log file for hierarchy decisions

    }

**Missing items?**

- Items must have both Item code and Description  ]```bash

- Empty rows are skipped automatically

- Check column mappings in settings.yaml}pip install -r requirements.txt


``````



## ConfigurationOr if using a virtual environment:



Edit `config/settings.yaml` to customize:```bash

- Column namespython -m venv venv

- Output formatsource venv/bin/activate  # On Windows: venv\Scripts\activate

- Logging settingspip install -r requirements.txt

```

## Requirements

2. **Verify installation:**

- Python 3.8+```bash

- pandaspython -c "import pandas, openpyxl, pydantic; print('All dependencies installed!')"

- openpyxl```

- pyyaml

---

## Notes

## Project Structure

- Level "c" items are automatically flattened into level 3

- Empty rows and invalid data are skipped```

- Logs are saved in `logs/` directoryexcel_to_json_pipeline/

├── config/
│   └── settings.yaml          # Configuration file
├── src/
│   ├── __init__.py
│   ├── models.py              # Pydantic data models
│   ├── excel_parser.py        # Excel file parsing
│   ├── hierarchy_processor.py # Hierarchy building (ignores 'c' levels)
│   ├── json_exporter.py       # JSON export functionality
│   └── pipeline.py            # Main orchestrator
├── input/                     # Place input Excel files here
├── output/                    # Generated JSON files (one per sheet)
├── logs/                      # Log files
├── requirements.txt           # Python dependencies
├── run.sh                     # Quick run script
├── process_separate_sheets.py # Convenience script
└── README.md                  # This file
```

---

## Usage

### Method 1: Quick Run (Recommended)

```bash
./run.sh
```

This processes all Excel files in the `input/` directory and creates separate JSON files for each sheet.

### Method 2: Using Process Script

```bash
python process_separate_sheets.py
```

Interactive script that guides you through processing.

### Method 3: Command Line (Advanced)

#### Process a single Excel file (separate files per sheet - default):

```bash
python src/pipeline.py input/your_file.xlsx
```

#### Export all sheets to one combined JSON file:

```bash
python src/pipeline.py input/your_file.xlsx --output-mode single
```

#### Process all Excel files in input directory:

```bash
python src/pipeline.py --batch
```

#### Process specific sheets only:

```bash
python src/pipeline.py input/your_file.xlsx --sheets "Sheet1" "Sheet2"
```

#### Use custom configuration:

```bash
python src/pipeline.py input/your_file.xlsx --config path/to/config.yaml
```

### Method 4: Python API

```python
from pathlib import Path
from src.pipeline import Pipeline

# Initialize pipeline
pipeline = Pipeline()

# Process a single file (separate JSON per sheet)
output_files = pipeline.process_file(
    input_file=Path("input/your_file.xlsx"),
    output_mode="multiple"  # default: one file per sheet
)

# Process as single combined file
output_file = pipeline.process_file(
    input_file=Path("input/your_file.xlsx"),
    output_mode="single"  # all sheets in one JSON
)

# Process all files in a directory
results = pipeline.process_directory(
    input_dir=Path("input"),
    output_mode="multiple"
)
```

---

## Hierarchy Logic

### Important: 'c' Levels Are Ignored ✨

The pipeline **ignores all 'c' subcategory levels** for simplified output. Items are placed **directly under their numeric parent levels**.

### Hierarchy Levels

The pipeline understands the following hierarchy indicators:

1. **Numeric Levels** (1, 2, 3, 4, ...): Main category levels defining depth
   - Higher numbers indicate deeper nesting
   - Items belong to the most recent numeric level
   - **Example**: Level 1 → Level 2 → Level 3 → Items

2. **Subcategory Indicator** ('c'): **IGNORED** - Skipped during processing
   - ~~Used to be subcategories within current level~~
   - Now completely ignored to simplify hierarchy
   - Items go directly under the numeric level

3. **Item Codes** (A, B, C, ...): Actual items with details
   - These are leaf nodes containing rates, units, descriptions
   - Placed directly under the most recent numeric level
   - All 'c' levels between numeric level and items are removed

### Before vs After

#### Before (With 'c' Subcategories)
```
Level 3: EARTHWORK
  └─ c: Excavation                    ← 'c' subcategory
      ├─ Item A: Manual excavation
      └─ Item B: Machine excavation
  └─ c: Backfilling                   ← 'c' subcategory
      └─ Item C: Manual backfill
```

#### After (Without 'c' Subcategories) ✨
```
Level 3: EARTHWORK
  ├─ Item A: Manual excavation        ← Directly under numeric level
  ├─ Item B: Machine excavation       ← Directly under numeric level
  └─ Item C: Manual backfill          ← Directly under numeric level
```

**Result**: 91% file size reduction (173 MB → 16 MB)

### Excel Format

Expected column structure:
- **Column 0**: Level indicator (numeric: 1, 2, 3... or 'c' which is ignored)
- **Column 1**: Item code (A, B, C, etc.)
- **Column 2**: Bill description
- **Column 3**: Unit (m3, m2, etc.)
- **Column 4**: Rate
- **Column 5**: Trade (optional)
- **Column 6**: Code (optional)
- **Column 7**: Full description (optional)

---

## Configuration

Edit `config/settings.yaml` to customize:

```yaml
# Input/Output settings
input_directory: "input"
output_directory: "output"
log_directory: "logs"

# Excel parsing settings
excel:
  level_column_index: 0
  item_column_index: 1
  description_column_index: 2
  unit_column_index: 3
  rate_column_index: 4

# Hierarchy processing
hierarchy:
  subcategory_indicator: "c"
  numeric_level_pattern: "^[0-9]+$"

# Logging settings
logging:
  level: "INFO"  # DEBUG, INFO, WARNING, ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Output Format

### Default: Separate Files Per Sheet

By default, each sheet is exported as a separate JSON file:

**Example with 3 sheets:**
```
output/
├── example_sheet1.json
├── example_sheet2.json
└── example_sheet3.json
```

### Alternative: Single Combined File

Use `--output-mode single` to export all sheets in one file.

### JSON Structure (Simplified - No 'c' levels)

```json
{
  "filename": "example.xlsx",
  "sheets": [
    {
      "sheet_name": "3-Hilton",
      "hierarchy": [
        {
          "level": 1,
          "description": "SECTION B - SITE WORK",
          "item_type": "numeric_level",
          "children": [
            {
              "level": 2,
              "description": "EARTHWORK",
              "item_type": "numeric_level",
              "children": [
                {
                  "level": 3,
                  "description": "B4 - SITE PREPARATION",
                  "item_type": "numeric_level",
                  "children": [
                    {
                      "item_code": "A",
                      "description": "Allow for taking over obligations",
                      "item_type": "item",
                      "level": 4,
                      "row_number": 14
                    },
                    {
                      "item_code": "B",
                      "description": "Anti-termite treatment",
                      "unit": "m²",
                      "rate": 21.59,
                      "item_type": "item",
                      "level": 4,
                      "row_number": 18
                    }
                  ]
                }
              ]
            }
          ]
        }
      ]
    }
  ]
}
```

**Note**: No 'c' subcategory levels - items go directly under numeric levels!

---

## Logging

Logs are saved in the `logs/` directory with timestamps. Each run creates a new log file:
- Format: `pipeline_YYYYMMDD_HHMMSS.log`
- Logs include INFO, WARNING, and ERROR messages
- Console output mirrors log file

## Error Handling

- Invalid Excel files are logged and skipped in batch mode
- Empty sheets are logged and skipped
- Malformed data is handled gracefully with warnings
- Full stack traces are logged for debugging

## Examples

### Example 1: Simple Hierarchy (After 'c' Level Removal)

**Excel Input:**
```
Level | Item | Description
------|------|-------------
1     |      | Main Category
c     |      | Subcategory (IGNORED)
      | A    | Item A
      | B    | Item B
2     |      | Another Category
      | C    | Item C
```

**JSON Output:**
```json
{
  "hierarchy": [
    {
      "level": 1,
      "description": "Main Category",
      "children": [
        {"item_code": "A", "description": "Item A", "item_type": "item"},
        {"item_code": "B", "description": "Item B", "item_type": "item"}
      ]
    },
    {
      "level": 2,
      "description": "Another Category",
      "children": [
        {"item_code": "C", "description": "Item C", "item_type": "item"}
      ]
    }
  ]
}
```

### Example 2: Real World BOQ

**Excel Input:**
```
Level | Item | Description                    | Unit | Rate
------|------|--------------------------------|------|-------
1     |      | SECTION B - SITE WORK          |      |
2     |      | EARTHWORK                      |      |
3     |      | B4 - SITE PREPARATION          |      |
c     |      | Excavation (IGNORED)           |      |
      | A    | Manual excavation              | m3   | 50.00
      | B    | Machine excavation             | m3   | 25.00
c     |      | Backfilling (IGNORED)          |      |
      | C    | Manual backfill                | m3   | 35.00
```

**JSON Output (Simplified):**
```json
{
  "level": 3,
  "description": "B4 - SITE PREPARATION",
  "children": [
    {
      "item_code": "A",
      "description": "Manual excavation",
      "unit": "m3",
      "rate": 50.00
    },
    {
      "item_code": "B",
      "description": "Machine excavation",
      "unit": "m3",
      "rate": 25.00
    },
    {
      "item_code": "C",
      "description": "Manual backfill",
      "unit": "m3",
      "rate": 35.00
    }
  ]
}
```

All 'c' levels are removed, items go directly under Level 3!

---

## Performance & File Sizes

### Real-World Results

Processing "Candy Jobs for UR Allocation Tool (with unit rates).xlsx":

| Sheet | Items | File Size | Processing Time |
|-------|-------|-----------|-----------------|
| 1-Master (no UR) | 5,845 | 3.0 MB | ~0.5s |
| 2-Terminal | 6,558 | 3.5 MB | ~0.6s |
| 3-Hilton | 5,210 | 1.5 MB | ~0.5s |
| 4-Resort Core | 796 | 372 KB | ~0.1s |
| 5-Remote Apron | 248 | 124 KB | ~0.1s |
| 6-ES85-Al Thumama | 2,082 | 1.7 MB | ~0.3s |
| 7-Imam Muslim | 452 | 236 KB | ~0.1s |
| 8-KKR | 2,498 | 1.3 MB | ~0.3s |
| 9-PA | 563 | 320 KB | ~0.1s |
| 10-One Hotel | 7,137 | 4.0 MB | ~0.7s |
| **TOTAL** | **31,389** | **~16 MB** | **~3.3s** |

**File Size Comparison:**
- Before (with 'c' levels): **173 MB**
- After (without 'c' levels): **16 MB**
- **Reduction: 91% smaller!** 🎉

---

## Troubleshooting

### No output files generated
- Check that Excel files are in the `input/` directory
- Verify file extension is `.xlsx` (not `.xls`)
- Check logs in `logs/` directory for error messages
- Ensure Python dependencies are installed: `pip install -r requirements.txt`

### Incorrect hierarchy
- Review the level column values (should be numeric: 1, 2, 3...)
- Remember: 'c' levels are now **ignored** - items go under numeric levels
- Check for empty rows that might break the hierarchy

### Missing data
- Verify column indices in `config/settings.yaml` match your Excel structure
- Check that data starts from the correct row
- Ensure required columns (level, item_code, description) have values

### Files too large
- This should be rare now with 'c' levels removed (91% reduction)
- If still large, check for excessive nesting or duplicate data
- Consider processing sheets individually

### Permission errors
- Ensure you have write permissions to `output/` and `logs/` directories
- Close Excel file before processing (some systems lock open files)

---

## Next Steps: Vector Store Preparation

After generating JSON files, you can prepare them for vector store ingestion using the companion module:

```bash
cd ../json_to_vectorstore
python prepare_vectorstore.py
```

This will:
- Extract only the actual items (leaf nodes)
- Use descriptions as text for embedding
- Preserve all metadata (rates, units, categories)
- Export as JSONL format (ready for Pinecone, Weaviate, Qdrant, etc.)

See `../json_to_vectorstore/README.md` for details.

---

### Running Tests

```bash
python -m pytest tests/
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### Code Structure

- **models.py**: Pydantic models defining data structures
- **excel_parser.py**: Excel file reading and initial data extraction
- **hierarchy_processor.py**: Core logic for building tree structure (ignores 'c' levels)
- **json_exporter.py**: JSON serialization and file writing
- **pipeline.py**: Orchestrates the entire process

### Adding New Features

1. **Update models** in `models.py` if data structure changes
2. **Modify parsers** in `excel_parser.py` for new Excel formats
3. **Adjust hierarchy logic** in `hierarchy_processor.py` for new rules
4. **Update exporters** in `json_exporter.py` for new output formats

### Key Implementation Detail

The 'c' level ignoring happens in `hierarchy_processor.py`:

```python
def _build_hierarchy(self, items: List[RawItem]) -> List[HierarchyItem]:
    # ...
    elif item.item_type == ItemType.SUBCATEGORY:
        # Skip 'c' subcategory levels entirely
        logger.debug(f"Skipping c level: {item.description}")
        pass  # Don't add to hierarchy, don't change current_parents
```

---

## Version History

### Version 2.0 (November 2024)
- ✨ **Major Change**: 'c' subcategory levels now ignored
- 📁 **Default changed**: Separate files per sheet (was single file)
- 🎯 **91% file size reduction**: 173 MB → 16 MB
- ⚡ **Faster processing**: Simpler hierarchy structure
- 📝 **Improved logging**: More detailed processing information

### Version 1.0 (2024)
- Initial release
- Excel parsing with hierarchy support
- JSON export with single/multiple modes
- Batch processing capability
- Comprehensive logging

---

## License

Proprietary - Internal Use Only

---

## Support

For issues, questions, or feature requests, contact the development team.

---

**Ready to convert your Excel files!** 🚀

```bash
./run.sh
```
