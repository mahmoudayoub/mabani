"""
Configuration manager for dynamic workflows options.
Reads/Writes configuration to the ReportsTable (PK=CONFIG).
"""

import os
import boto3
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError

class ConfigManager:
    """Manages dynamic configuration in DynamoDB."""
    
    def __init__(self, table_name: Optional[str] = None):
        self.table_name = table_name or os.environ.get("REPORTS_TABLE")
        if not self.table_name:
             self.table_name = "taskflow-backend-dev-reports" # Fallback
             
        self.dynamodb = boto3.resource("dynamodb")
        self.table = self.dynamodb.Table(self.table_name)
        
    def get_options(self, config_type: str) -> List[str]:
        """
        Get options for a specific type (e.g. 'LOCATIONS', 'BREACH_SOURCES').
        Returns list of strings.
        """
        try:
            # PK=CONFIG, SK=TYPE
            response = self.table.get_item(
                Key={
                    "PK": "CONFIG",
                    "SK": config_type.upper()
                }
            )
            item = response.get("Item")
            if item and "values" in item:
                return item["values"]
            
            # Return defaults if not found
            return self._get_defaults(config_type)
            
        except ClientError as e:
            print(f"Error fetching config {config_type}: {e}")
            return self._get_defaults(config_type)

    def _get_defaults(self, config_type: str) -> List[str]:
        """Return hardcoded defaults if DB is empty."""
        defaults = {
            "LOCATIONS": [
                "Main Building",
                "Site Office",
                "Working Area A",
                "Working Area B",
                "Storage Yard",
                "Roof Level"
            ],
            "HAZARD_TAXONOMY": [
                "A1 Confined Spaces", "A2 Electrical Safety", "A3 Excavation & Trenching", "A4 Fire Prevention",
                "A5 Hazardous Materials", "A6 Hot Works", "A7 Housekeeping", "A8 Lifting Operations",
                "A9 Lighting", "A10 Manual Handling", "A11 Material Storage", "A12 Mobile Plant & Equipment",
                "A13 Site Welfare Facilities", "A14 Tunnelling", "A15 Working at Height / Fall Protection",
                "A16 Working on or Near Live Roads", "A17 Working on or near Water", "A18 Man & Machine Interface",
                "A19 Traffic Management", "A20 Formwork & Falsework", "A21 Scaffolding", "A22 Emergency Response",
                "A23 Security", "A24 Signage & Communication", "A25 Hand & Power Tools", "A26 Site Establishment",
                "A27 Airside Safety", "A28 Lock-Out / Tag-Out", "A29 Permit to Work", "A30 Radiation Safety",
                "A31 Site Logistics", "A32 Subcontractor Management", "A33 Training & Awareness", "A34 Underground Utilities",
                "A35 Access / Egress", "A36 Barrication", "A37 Public Safety & Protection", "A38 Safety Devices / Equipment",
                "A39 PPE", "A40 Documentation", "A41 Others",
                "B1 Noise", "B2 Environmental Protection", "B3 Waste Management", "B4 Dust Suppression & Emissions",
                "B5 Air Emissions & Quality", "B6 Flora & Fauna", "B7 Soil Erosion", "B8 Water Discharge / Contamination",
                "B9 Groundwater Protection", "B10 Flood Mitigation", "B11 Sustainability",
                "C1 Working in the Heat", "C2 Ergonomics", "C3 Occupational Health", "C4 Pest Control"
            ],
            "OBSERVATION_TYPES": [
                "Unsafe Act",
                "Unsafe Condition",
                "Near Miss",
                "Positive Observation"
            ],
            "BREACH_SOURCES": [
                "Subcontractor A",
                "Subcontractor B",
                "Internal Staff",
                "Visitor",
                "Equipment Failure"
            ],
            "SEVERITY_LEVELS": [
                "High",
                "Medium",
                "Low"
            ]
        }
        return defaults.get(config_type.upper(), [])
