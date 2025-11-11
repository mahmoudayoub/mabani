#!/usr/bin/env python3
"""
Simple wrapper - processes all Excel files in input/ folder
and saves results to output/ folder.
"""
import sys
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from rate_filler_pipeline
from rate_filler_pipeline.fill_rates import run_pipeline

# Load environment from root .env
load_dotenv(Path(__file__).parent.parent / '.env')


def get_sheet_names(excel_file: Path) -> list:
    """Get all sheet names from Excel file."""
    try:
        xl = pd.ExcelFile(excel_file)
        return xl.sheet_names
    except Exception as e:
        print(f"Warning: Could not read sheets from {excel_file.name}: {e}")
        return []


def main():
    """Process all Excel files from input folder."""
    
    # Get directories
    script_dir = Path(__file__).parent
    input_dir = script_dir / 'input'
    output_dir = script_dir / 'output'
    
    # Create directories if they don't exist
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    print("=" * 80)
    print("BOQ RATE FILLER - AUTO PROCESSOR")
    print("=" * 80)
    print()
    print(f"📂 Input folder:  {input_dir}")
    print(f"📂 Output folder: {output_dir}")
    print()
    
    # Find Excel files in input folder
    excel_files = list(input_dir.glob('*.xlsx')) + list(input_dir.glob('*.xls'))
    
    # Filter out temp files (starting with ~$)
    excel_files = [f for f in excel_files if not f.name.startswith('~$')]
    
    if not excel_files:
        print("❌ No Excel files found in input folder!")
        print()
        print("📋 To use this:")
        print(f"   1. Copy your Excel file(s) to: {input_dir}")
        print(f"   2. Run: python process_folder.py")
        print(f"   3. Find results in: {output_dir}")
        print()
        return 1
    
    print(f"📊 Found {len(excel_files)} Excel file(s):")
    for f in excel_files:
        sheets = get_sheet_names(f)
        if sheets:
            print(f"   - {f.name} ({len(sheets)} sheets)")
        else:
            print(f"   - {f.name}")
    print()
    
    # Ask which sheet(s) to process
    print("Sheet processing mode:")
    print("  1. Process first sheet only")
    print("  2. Process ALL sheets in each file")
    print("  3. Specify sheet name")
    print()
    mode = input("Select mode (1/2/3): ").strip()
    
    sheet_name = None
    process_all_sheets = False
    
    if mode == '1':
        print("Will process first sheet in each file")
    elif mode == '2':
        process_all_sheets = True
        print("Will process ALL sheets in each file")
    elif mode == '3':
        sheet_name = input("Enter sheet name: ").strip()
        print(f"Will process sheet '{sheet_name}' in each file")
    else:
        print("Invalid choice. Defaulting to first sheet only.")
    
    print()
    response = input("Proceed? (y/n): ").strip().lower()
    if response != 'y':
        print("Cancelled.")
        return 0
    
    print()
    
    # Process each file
    success_count = 0
    failed_count = 0
    
    for idx, excel_file in enumerate(excel_files, 1):
        print("=" * 80)
        print(f"Processing file {idx}/{len(excel_files)}: {excel_file.name}")
        print("=" * 80)
        print()
        
        try:
            # Determine which sheets to process
            if process_all_sheets:
                sheets_to_process = get_sheet_names(excel_file)
                if not sheets_to_process:
                    print(f"⚠️  No sheets found in {excel_file.name}, skipping")
                    failed_count += 1
                    continue
            elif sheet_name:
                sheets_to_process = [sheet_name]
            else:
                sheets_to_process = get_sheet_names(excel_file)
                if sheets_to_process:
                    sheets_to_process = [sheets_to_process[0]]  # First sheet only
                else:
                    print(f"⚠️  No sheets found in {excel_file.name}, skipping")
                    failed_count += 1
                    continue
            
            # Process each sheet
            file_success = True
            for sheet in sheets_to_process:
                print(f"\n📄 Processing sheet: '{sheet}'")
                try:
                    output_path = run_pipeline(
                        input_excel=str(excel_file),
                        sheet_name=sheet,
                        output_excel=None,  # Auto-generate in output folder
                        similarity_threshold=0.76,
                        top_k=6
                    )
                    
                    if output_path:
                        print(f"   ✅ Success! Output: {Path(output_path).name}")
                    else:
                        print(f"   ⚠️  Warning: No output generated for sheet '{sheet}'")
                        file_success = False
                        
                except Exception as e:
                    print(f"   ❌ Error processing sheet '{sheet}': {e}")
                    file_success = False
            
            if file_success:
                success_count += 1
            else:
                failed_count += 1
            print()
        
        except Exception as e:
            failed_count += 1
            print()
            print(f"❌ Error processing {excel_file.name}: {e}")
        
        print()
    
    # Summary
    print("=" * 80)
    print("PROCESSING COMPLETE")
    print("=" * 80)
    print()
    print(f"📊 Summary:")
    print(f"   Total files: {len(excel_files)}")
    print(f"   ✅ Success: {success_count}")
    print(f"   ❌ Failed: {failed_count}")
    print()
    print(f"📁 All outputs saved to: {output_dir}")
    print()
    
    return 0 if failed_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
