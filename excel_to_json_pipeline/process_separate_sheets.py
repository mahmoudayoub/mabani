"""
Process Excel files with each sheet saved as a separate JSON file.
This is now the default behavior.
"""
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from pipeline import Pipeline

def main():
    """Process Excel files with separate JSON output per sheet."""
    print("=" * 80)
    print("Excel to JSON Pipeline - Separate Files Per Sheet")
    print("=" * 80)
    
    # Initialize pipeline
    pipeline = Pipeline()
    
    # Find Excel files in input directory
    input_dir = Path(__file__).parent / 'input'
    excel_files = list(input_dir.glob('*.xlsx'))
    
    if not excel_files:
        print("\n❌ No Excel files found in input directory!")
        print(f"Please place Excel files in: {input_dir}")
        return 1
    
    print(f"\n✓ Found {len(excel_files)} Excel file(s):")
    for f in excel_files:
        print(f"  • {f.name}")
    
    print("\n" + "=" * 80)
    print("Processing...")
    print("=" * 80)
    
    all_outputs = []
    
    for excel_file in excel_files:
        try:
            print(f"\n📂 Processing: {excel_file.name}")
            
            # Process with separate file per sheet
            output_paths = pipeline.process_file(
                input_file=excel_file,
                output_mode='multiple'  # Each sheet → separate JSON
            )
            
            all_outputs.extend(output_paths)
            
            print(f"✓ Generated {len(output_paths)} JSON file(s)")
            for path in output_paths:
                size = path.stat().st_size
                if size > 1024 * 1024:
                    size_str = f"{size / (1024 * 1024):.2f} MB"
                elif size > 1024:
                    size_str = f"{size / 1024:.2f} KB"
                else:
                    size_str = f"{size} bytes"
                print(f"  • {path.name} ({size_str})")
                
        except Exception as e:
            print(f"❌ Error processing {excel_file.name}: {e}")
            continue
    
    print("\n" + "=" * 80)
    print("✅ COMPLETE!")
    print("=" * 80)
    print(f"\nTotal JSON files generated: {len(all_outputs)}")
    print(f"Output directory: {Path(__file__).parent / 'output'}")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
