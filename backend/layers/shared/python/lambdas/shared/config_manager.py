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
                # Safety (41 categories)
                {"id": 1, "name": "Confined Spaces", "category": "Safety"},
                {"id": 2, "name": "Electrical Safety", "category": "Safety"},
                {"id": 3, "name": "Excavation & Trenching", "category": "Safety"},
                {"id": 4, "name": "Fire Prevention", "category": "Safety"},
                {"id": 5, "name": "Hazardous Materials", "category": "Safety"},
                {"id": 6, "name": "Hot Works", "category": "Safety"},
                {"id": 7, "name": "Housekeeping", "category": "Safety"},
                {"id": 8, "name": "Lifting Operations", "category": "Safety"},
                {"id": 9, "name": "Lighting", "category": "Safety"},
                {"id": 10, "name": "Manual Handling", "category": "Safety"},
                {"id": 11, "name": "Material Storage", "category": "Safety"},
                {"id": 12, "name": "Mobile Plant & Equipment", "category": "Safety"},
                {"id": 13, "name": "Site Welfare Facilities", "category": "Safety"},
                {"id": 14, "name": "Tunnelling", "category": "Safety"},
                {"id": 15, "name": "Working at Height / Fall Protection", "category": "Safety"},
                {"id": 16, "name": "Working on or Near Live Roads", "category": "Safety"},
                {"id": 17, "name": "Working on or near Water", "category": "Safety"},
                {"id": 18, "name": "Man & Machine Interface", "category": "Safety"},
                {"id": 19, "name": "Traffic Management", "category": "Safety"},
                {"id": 20, "name": "Formwork & Falsework", "category": "Safety"},
                {"id": 21, "name": "Scaffolding", "category": "Safety"},
                {"id": 22, "name": "Emergency Response", "category": "Safety"},
                {"id": 23, "name": "Security", "category": "Safety"},
                {"id": 24, "name": "Signage & Communication", "category": "Safety"},
                {"id": 25, "name": "Hand & Power Tools", "category": "Safety"},
                {"id": 26, "name": "Site Establishment", "category": "Safety"},
                {"id": 27, "name": "Airside Safety", "category": "Safety"},
                {"id": 28, "name": "Lock-Out / Tag-Out", "category": "Safety"},
                {"id": 29, "name": "Permit to Work", "category": "Safety"},
                {"id": 30, "name": "Radiation Safety", "category": "Safety"},
                {"id": 31, "name": "Site Logistics", "category": "Safety"},
                {"id": 32, "name": "Subcontractor Management", "category": "Safety"},
                {"id": 33, "name": "Training & Awareness", "category": "Safety"},
                {"id": 34, "name": "Underground Utilities", "category": "Safety"},
                {"id": 35, "name": "Access / Egress", "category": "Safety"},
                {"id": 36, "name": "Barrication", "category": "Safety"},
                {"id": 37, "name": "Public Safety & Protection", "category": "Safety"},
                {"id": 38, "name": "Safety Devices / Equipment", "category": "Safety"},
                {"id": 39, "name": "PPE", "category": "Safety"},
                {"id": 40, "name": "Documentation", "category": "Safety"},
                {"id": 41, "name": "Others", "category": "Safety"},
                # Environmental (11 categories)
                {"id": 42, "name": "Noise", "category": "Environmental"},
                {"id": 43, "name": "Environmental Protection", "category": "Environmental"},
                {"id": 44, "name": "Waste Management", "category": "Environmental"},
                {"id": 45, "name": "Dust Suppression & Emissions", "category": "Environmental"},
                {"id": 46, "name": "Air Emissions & Quality", "category": "Environmental"},
                {"id": 47, "name": "Flora & Fauna", "category": "Environmental"},
                {"id": 48, "name": "Soil Erosion", "category": "Environmental"},
                {"id": 49, "name": "Water Discharge / Contamination", "category": "Environmental"},
                {"id": 50, "name": "Groundwater Protection", "category": "Environmental"},
                {"id": 51, "name": "Flood Mitigation", "category": "Environmental"},
                {"id": 52, "name": "Sustainability", "category": "Environmental"},
                # Health (4 categories)
                {"id": 53, "name": "Working in the Heat", "category": "Health"},
                {"id": 54, "name": "Ergonomics", "category": "Health"},
                {"id": 55, "name": "Occupational Health", "category": "Health"},
                {"id": 56, "name": "Pest Control", "category": "Health"}
            ],
            "OBSERVATION_TYPES": [
                "Unsafe Condition (UC)",
                "Unsafe Act (UA)",
                "Near Miss (NM)",
                "Good Practice (GP)"
            ],
            "BREACH_SOURCES": [
                "Almabani",
                "Subcontractor"
            ],
            "SEVERITY_LEVELS": [
                "High",
                "Medium",
                "Low"
            ],
            "STOPPAGE_OPTIONS": [
                "Yes",
                "No"
            ],
            "RESPONSIBLE_PERSONS": [
                "Site Engineer A",
                "Site Engineer B",
                "Safety Officer X",
                "Project Manager Y"
            ],
            "PROJECTS": [
                "Riyadh Metro Line 3",
                "King Salman Park",
                "Red Sea Airport",
                "Diriyah Gate",
                "NEOM The Line"
            ]
        }
        return defaults.get(config_type.upper(), [])
