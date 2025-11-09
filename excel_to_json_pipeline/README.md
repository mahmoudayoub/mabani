# Excel to JSON Pipeline# Excel to JSON Pipeline



Convert Excel BOQ files to structured JSON format with hierarchical organization.A production-level, modular pipeline for converting Excel files with hierarchical BOQ (Bill of Quantities) data into JSON format.



## Overview## Table of Contents

- [Features](#features)

This pipeline processes Excel files containing Bill of Quantities (BOQ) data and converts them into structured JSON format. It preserves the hierarchical structure (levels 1, 2, 3) while flattening level "c" entries.- [Key Improvements](#key-improvements)

- [Quick Start](#quick-start)

## Features- [Installation](#installation)

- [Project Structure](#project-structure)

- ✅ Process multiple sheets from Excel files- [Usage](#usage)

- ✅ Hierarchical organization (Level 1 → Level 2 → Level 3)- [Hierarchy Logic](#hierarchy-logic)

- ✅ Automatic level "c" flattening- [Configuration](#configuration)

- ✅ Separate JSON file per sheet- [Output Format](#output-format)

- ✅ Preserves item codes, descriptions, units, and rates- [Logging](#logging)

- [Examples](#examples)

## Directory Structure- [Performance & File Sizes](#performance--file-sizes)

- [Troubleshooting](#troubleshooting)

```- [Next Steps: Vector Store Preparation](#next-steps-vector-store-preparation)

excel_to_json_pipeline/- [Development](#development)

├── src/                      # Core modules- [Version History](#version-history)

│   ├── excel_parser.py       # Excel file reading

│   ├── hierarchy_processor.py # Hierarchy management---

│   ├── json_exporter.py      # JSON output

│   ├── models.py             # Data models## Features

│   └── pipeline.py           # Main pipeline

├── config/✨ **Modular Architecture**: Separate modules for parsing, processing, and exporting  

│   └── settings.yaml         # Configuration📊 **Hierarchical Processing**: Builds tree structure from numeric levels  

├── input/                    # Place Excel files here🎯 **Simplified Structure**: Ignores 'c' subcategory levels for cleaner output  

├── output/                   # Generated JSON files🔒 **Type Safety**: Uses Pydantic models for data validation  

├── logs/                     # Log files⚙️ **Flexible Configuration**: YAML-based configuration for easy customization  

├── process_separate_sheets.py # Main script📝 **Comprehensive Logging**: Detailed logging for debugging and monitoring  

├── requirements.txt          # Dependencies📦 **Batch Processing**: Process single files or entire directories  

└── README.md                 # This file📁 **Multiple Output Modes**: Separate JSON file per sheet (default) or single combined file  

```

## Key Improvements

## Installation

**91% File Size Reduction**: By ignoring 'c' subcategory levels, output files are dramatically smaller (173 MB → 16 MB)

```bash

# Install dependencies**Simpler Hierarchy**: Items placed directly under numeric levels instead of nested under 'c' subcategories

pip install -r requirements.txt

```**Separate Files by Default**: Each sheet exports as individual JSON file for easier management



## Usage## Quick Start



1. **Place Excel files** in the `input/` directory**Fastest way to get started:**



2. **Run the pipeline:**```bash

   ```bash# 1. Place your Excel file in the input directory

   cd excel_to_json_pipelinecp "your_file.xlsx" input/

   python process_separate_sheets.py

   ```# 2. Run the pipeline (using convenience script)

./run.sh

3. **Output:** JSON files will be created in `output/` directory

   - One JSON file per Excel sheet# Or using the process script directly

   - Format: `{original_filename}_{sheet_name}.json`python process_separate_sheets.py

```

## Input Format

That's it! Check the `output/` directory for your JSON files (one per sheet).

Excel file should have these columns:

- **Level**: Hierarchy level (1, 2, 3, or c)---

- **Item**: Item code

- **Bill description**: Item description## Installation

- **Unit**: Unit of measurement

- **Rate**: Unit rate```

excel_to_json_pipeline/

## Output Format├── config/

│   └── settings.yaml          # Configuration file

```json├── src/

{│   ├── __init__.py

  "source_file": "example.xlsx",│   ├── models.py              # Pydantic data models

  "source_sheet": "Sheet1",│   ├── excel_parser.py        # Excel file parsing

  "hierarchy": [│   ├── hierarchy_processor.py # Hierarchy building logic

    {│   ├── json_exporter.py       # JSON export functionality

      "level": 1,│   └── pipeline.py            # Main orchestrator

      "code": "1",├── input/                     # Place input Excel files here

      "description": "Main Category",├── output/                    # Generated JSON files

      "children": [├── logs/                      # Log files

        {├── requirements.txt           # Python dependencies

          "level": 2,└── README.md                  # This file

          "code": "1.1",```

          "description": "Sub Category",

          "children": [---

            {

              "level": 3,## Installation

              "code": "1.1.1",

              "description": "Item Description",### Prerequisites

              "unit": "m2",- Python 3.8 or higher

              "rate": 100.50- pip package manager

            }

          ]### Setup

        }

      ]1. **Install Python dependencies:**

    }

  ]```bash

}pip install -r requirements.txt

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
