#!/usr/bin/env python3
"""
Simple wrapper - process a single file from input folder by name.
Usage: python process_single.py filename.xlsx
"""
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path for absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from rate_filler_pipeline
from rate_filler_pipeline.fill_rates import run_pipeline

# Load environment from root .env
load_dotenv(Path(__file__).parent.parent / '.env')


def main():
    """Process a single Excel file from input folder."""
    
    if len(sys.argv) < 3:
        print("Usage: python process_single.py <filename.xlsx> <sheet_name>")
        print()
        print("Example:")
        print("  python process_single.py my_boq.xlsx 'Terminal'")
        print()
        print("Note: File must be in the 'input/' folder")
        return 1
    
    # Get directories
    script_dir = Path(__file__).parent
    input_dir = script_dir / 'input'
    output_dir = script_dir / 'output'
    
    # Create directories
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)
    
    # Get input file and sheet name
    filename = sys.argv[1]
    sheet_name = sys.argv[2]
    input_file = input_dir / filename
    
    if not input_file.exists():
        print(f"❌ Error: File not found: {input_file}")
        print()
        print(f"Make sure '{filename}' is in the input folder:")
        print(f"  {input_dir}")
        return 1
    
    print("=" * 80)
    print("BOQ RATE FILLER - SINGLE FILE PROCESSOR")
    print("=" * 80)
    print()
    print(f"📥 Input:  {input_file.name}")
    print(f"� Sheet:  {sheet_name}")
    print(f"�📤 Output: output/{input_file.stem}_filled_TIMESTAMP.xlsx")
    print()
    
    # Parse optional arguments
    threshold = 0.5
    top_k = 6
    
    for i, arg in enumerate(sys.argv):
        if arg == '--threshold' and i + 1 < len(sys.argv):
            threshold = float(sys.argv[i + 1])
        if arg == '--top-k' and i + 1 < len(sys.argv):
            top_k = int(sys.argv[i + 1])
    
    # Run pipeline
    try:
        output_path = run_pipeline(
            input_excel=str(input_file),
            sheet_name=sheet_name,
            output_excel=None,  # Auto-generate in output folder
            similarity_threshold=threshold,
            top_k=top_k
        )
        
        if output_path:
            print()
            print("=" * 80)
            print("✅ SUCCESS")
            print("=" * 80)
            print()
            print(f"📁 Filled Excel: {Path(output_path).name}")
            print(f"📁 Report: {Path(output_path).with_suffix('.txt').name}")
            print()
            print(f"Location: {output_dir}")
            print()
            return 0
        else:
            print()
            print("❌ No output generated")
            return 1
            
    except Exception as e:
        print()
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
