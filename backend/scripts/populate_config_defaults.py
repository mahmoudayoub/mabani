"""
Script to populate DynamoDB with default configuration values.
Run this once to initialize the CONFIG entries in the database.
"""

import boto3
import os

# Initialize DynamoDB
dynamodb = boto3.resource('dynamodb', region_name='eu-west-1')
table_name = 'taskflow-backend-dev-reports'
table = dynamodb.Table(table_name)

# Import defaults from config_manager
import sys
sys.path.insert(0, '/Users/mayoub/Desktop/Almabani/mabani/backend/lambdas')
from shared.config_manager import ConfigManager

def populate_defaults():
    """Populate the database with default configuration values."""
    config_manager = ConfigManager(table_name=table_name)
    
    # Configuration types to populate
    config_types = [
        "PROJECTS",
        "HAZARD_TAXONOMY",
        "OBSERVATION_TYPES",
        "BREACH_SOURCES",
        "SEVERITY_LEVELS",
        "STOPPAGE_OPTIONS",
        "RESPONSIBLE_PERSONS"
    ]
    
    for config_type in config_types:
        print(f"Populating {config_type}...")
        
        # Get the defaults
        defaults = config_manager._get_defaults(config_type)
        
        if not defaults:
            print(f"  ⚠️  No defaults found for {config_type}")
            continue
        
        # Write to DynamoDB
        try:
            table.put_item(
                Item={
                    "PK": "CONFIG",
                    "SK": config_type.upper(),
                    "values": defaults
                }
            )
            print(f"  ✅ Successfully populated {config_type} ({len(defaults)} items)")
        except Exception as e:
            print(f"  ❌ Error populating {config_type}: {e}")
    
    print("\n✨ Database population complete!")

if __name__ == "__main__":
    print(f"Populating table: {table_name}")
    print(f"Region: eu-west-1")
    print("-" * 50)
    populate_defaults()
