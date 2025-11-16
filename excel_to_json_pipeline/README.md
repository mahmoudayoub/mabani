# Excel to JSON Pipeline

Convert Excel BOQ (Bill of Quantities) files into structured JSON format with hierarchical organization.

## Overview

This pipeline processes Excel files containing construction BOQ data and converts them into structured JSON format. It intelligently handles hierarchical levels (numeric levels 1, 2, 3, etc.) and consecutive c-level subcategories to create a clean, navigable data structure.

## Features

- ✅ **Hierarchical Processing**: Builds tree structure from numeric levels (PART 1, PART 2, etc.)
- ✅ **C-Level Logic**: Handles consecutive c-level subcategories with proper parent-child relationships
- ✅ **Multi-Sheet Support**: Process single sheets or all sheets in a workbook
- ✅ **Type Safety**: Pydantic models ensure data validation
- ✅ **Flexible Configuration**: YAML-based configuration for customization
- ✅ **Comprehensive Logging**: Detailed logs for debugging and monitoring
- ✅ **No API Dependencies**: Pure Python processing, no external API calls needed

## Directory Structure

```
excel_to_json_pipeline/
├── src/
│   ├── excel_parser.py          # Read Excel files and extract data
│   ├── hierarchy_processor.py   # Build hierarchical structure from levels
│   ├── json_exporter.py         # Export to JSON format
│   ├── models.py                # Pydantic data models
│   └── pipeline.py              # Main orchestration logic
├── config/
│   └── settings.yaml            # Configuration settings
├── input/                       # Place Excel files here
├── output/                      # Generated JSON files (one per sheet)
├── logs/                        # Processing logs with timestamps
├── process_separate_sheets.py  # Main entry point
└── requirements.txt             # Dependencies
```

## Installation

```bash
# From project root
pip install -r excel_to_json_pipeline/requirements.txt
```

## Configuration

The pipeline doesn't require API keys. All configuration is in `config/settings.yaml`:

```yaml
# Excel parsing settings
excel:
  # Column indices (0-based)
  level_column_index: 0
  item_column_index: 1
  description_column_index: 2
  unit_column_index: 3
  rate_column_index: 4
  
  # Start reading from row (0-based)
  data_start_row: 1
  
  # Skip empty rows
  skip_empty_rows: true

# Hierarchy processing
hierarchy:
  # Character indicating sub-category
  subcategory_indicator: "c"
  
  # Valid level patterns (numeric levels)
  numeric_level_pattern: "^[0-9]+$"
  
  # Item patterns (letters or alphanumeric codes)
  item_pattern: "^[A-Za-z0-9]+.*$"

# Output settings
output:
  indent: 2  # JSON indentation
  ensure_ascii: false  # Allow non-ASCII characters
```

**Key Settings:**

- `level_column_index`: Column containing level numbers (e.g., "1", "2", "c")
- `item_column_index`: Column containing item codes (e.g., "A", "B1", "C2a")
- `description_column_index`: Column with item descriptions
- `unit_column_index`: Column with units (m², kg, etc.)
- `rate_column_index`: Column with unit rates
- `data_start_row`: First row of actual data (skip header)
- `subcategory_indicator`: Character for sub-levels (usually "c")

## Usage

### Process All Sheets

```bash
# Place Excel file in input/ folder
cp "your_file.xlsx" excel_to_json_pipeline/input/

# Run pipeline (processes all sheets)
cd excel_to_json_pipeline
python process_separate_sheets.py

# Output: One JSON file per sheet in output/
# - Book1_Sheet1.json
# - Book1_Sheet2.json
# - etc.
```

## How It Works

### 1. Excel Parsing

The pipeline reads Excel files and identifies:
- **Header row**: Typically contains "Level", "Item", "Description", "Unit", "Pricing"
- **Data rows**: All rows below header
- **Hierarchy markers**: "Level" column with numeric values (1, 2, 3) or "c"

### 2. Hierarchy Building

**Level Structure:**
- **Level 1**: Top-level categories (e.g., "PART 1 - EARTHWORKS")
- **Level 2**: Subcategories (e.g., "General Excavation")
- **Level 3**: Detail level (e.g., "Excavation for foundations")
- **Level c**: Special consecutive levels handled with custom logic

**C-Level Logic:**

When consecutive c-levels appear:
1. First c followed by second c → Clear stack, add first to current parent
2. Second c followed by items → Add second c to stack
3. Items get: grandparent=first_c, parent=second_c

Example:
```
Level 2: General Excavation
  c: General Excavation: material excavated to be...
  c: Apron area
    Item: 3.1.02 | Depth not exceeding 0.25m

Result for item 3.1.02:
- Grandparent: "General Excavation: material excavated to be..."
- Parent: "Apron area"
- Description: "Depth not exceeding 0.25m"
```

### 3. JSON Export

Each sheet is exported as a separate JSON file with structure:

```json
{
  "sheet_name": "Terminal",
  "hierarchy": [
    {
      "level": 1,
      "description": "PART 1 - EARTHWORKS",
      "children": [
        {
          "level": 2,
          "description": "General Excavation",
          "children": [
            {
              "level": "c",
              "description": "General Excavation: material...",
              "items": [
                {
                  "item_code": "3.1.02",
                  "description": "Depth not exceeding 0.25m",
                  "unit": "m³",
                  "rate": 45.50,
                  "parent": "Apron area",
                  "grandparent": "General Excavation: material..."
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

## Output Format

### Item Fields
- **item_code**: Item reference number (e.g., "3.1.02")
- **description**: Item description text
- **unit**: Unit of measurement (m³, m², nr, etc.)
- **rate**: Unit rate/price (numeric)
- **parent**: Immediate parent description (from last c-level)
- **grandparent**: Second-level parent description (from first c-level)

### Hierarchy Fields
- **level**: Numeric (1, 2, 3) or "c"
- **description**: Level description text
- **children**: Nested sub-levels
- **items**: Array of items at this level

## Performance

Typical processing times:
- **Small files** (< 500 items): < 5 seconds
- **Medium files** (500-2000 items): 5-15 seconds
- **Large files** (2000+ items): 15-30 seconds

No API calls means processing is very fast and has no usage costs.

## Troubleshooting

### No items extracted?
- Check that "Level" column contains "c" markers
- Verify header row is correctly identified
- Review logs for parsing errors
- Ensure Excel file has standard structure

### Wrong hierarchy?
- Verify c-levels are in correct order
- Check for empty rows between c-levels (they're skipped)
- Review c-level logic in `hierarchy_processor.py`
- Check logs for hierarchy building steps

### Missing parent/grandparent?
- C-level logic requires at least 2 consecutive c-levels
- Single c-level items won't have grandparent
- Check that c-levels appear before items

## Integration with Other Pipelines

This pipeline is the **first step** in the BOQ processing workflow:

```
Excel Files
    ↓
[excel_to_json_pipeline]
    ↓
JSON Files
    ↓
[json_to_vectorstore]
    ↓
Pinecone Vector Database
    ↓
[rate_filler_pipeline]
    ↓
Filled Excel Files
```

---

**Version**: 2.0  
**Last Updated**: November 15, 2025  
**Status**: Production Ready
