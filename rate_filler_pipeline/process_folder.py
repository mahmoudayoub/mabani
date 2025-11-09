#!/usr/bin/env python3
"""
Simple wrapper - processes all Excel files in input/ folder
and saves results to output/ folder.
"""
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Import from rate_filler_pipeline
from rate_filler_pipeline.fill_rates import run_pipeline

# Load environment
load_dotenv()


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
        print(f"   - {f.name}")
    print()
    
    # Ask for confirmation
    response = input("Process these files? (y/n): ").strip().lower()
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
            # Run pipeline
            output_path = run_pipeline(
                input_excel=str(excel_file),
                output_excel=None,  # Auto-generate in output folder
                similarity_threshold=0.76,
                top_k=6
            )
            
            if output_path:
                success_count += 1
                print()
                print(f"✅ Success! Output: {Path(output_path).name}")
            else:
                failed_count += 1
                print()
                print(f"⚠️  Warning: No output generated")
        
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
