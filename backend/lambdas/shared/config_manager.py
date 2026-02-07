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
                # Safety (A)
                {"code": "A1", "name": "Confined Spaces", "category": "Safety"},
                {"code": "A2", "name": "Electrical Safety", "category": "Safety"},
                {"code": "A3", "name": "Excavation & Trenching", "category": "Safety"},
                {"code": "A4", "name": "Fire Prevention", "category": "Safety"},
                {"code": "A5", "name": "Hazardous Materials", "category": "Safety"},
                {"code": "A6", "name": "Hot Works", "category": "Safety"},
                {"code": "A7", "name": "Housekeeping", "category": "Safety"},
                {"code": "A8", "name": "Lifting Operations", "category": "Safety"},
                {"code": "A9", "name": "Lighting", "category": "Safety"},
                {"code": "A10", "name": "Manual Handling", "category": "Safety"},
                {"code": "A11", "name": "Material Storage", "category": "Safety"},
                {"code": "A12", "name": "Mobile Plant & Equipment", "category": "Safety"},
                {"code": "A13", "name": "Site Welfare Facilities", "category": "Safety"},
                {"code": "A14", "name": "Tunnelling", "category": "Safety"},
                {"code": "A15", "name": "Working at Height / Fall Protection", "category": "Safety"},
                {"code": "A16", "name": "Working on or Near Live Roads", "category": "Safety"},
                {"code": "A17", "name": "Working on or near Water", "category": "Safety"},
                {"code": "A18", "name": "Man & Machine Interface", "category": "Safety"},
                {"code": "A19", "name": "Traffic Management", "category": "Safety"},
                {"code": "A20", "name": "Formwork & Falsework", "category": "Safety"},
                {"code": "A21", "name": "Scaffolding", "category": "Safety"},
                {"code": "A22", "name": "Emergency Response", "category": "Safety"},
                {"code": "A23", "name": "Security", "category": "Safety"},
                {"code": "A24", "name": "Signage & Communication", "category": "Safety"},
                {"code": "A25", "name": "Hand & Power Tools", "category": "Safety"},
                {"code": "A26", "name": "Site Establishment", "category": "Safety"},
                {"code": "A27", "name": "Airside Safety", "category": "Safety"},
                {"code": "A28", "name": "Lock-Out / Tag-Out", "category": "Safety"},
                {"code": "A29", "name": "Permit to Work", "category": "Safety"},
                {"code": "A30", "name": "Radiation Safety", "category": "Safety"},
                {"code": "A31", "name": "Site Logistics", "category": "Safety"},
                {"code": "A32", "name": "Subcontractor Management", "category": "Safety"},
                {"code": "A33", "name": "Training & Awareness", "category": "Safety"},
                {"code": "A34", "name": "Underground Utilities", "category": "Safety"},
                {"code": "A35", "name": "Access / Egress", "category": "Safety"},
                {"code": "A36", "name": "Barrication", "category": "Safety"},
                {"code": "A37", "name": "Public Safety & Protection", "category": "Safety"},
                {"code": "A38", "name": "Safety Devices / Equipment", "category": "Safety"},
                {"code": "A39", "name": "PPE", "category": "Safety"},
                {"code": "A40", "name": "Documentation", "category": "Safety"},
                {"code": "A41", "name": "Others", "category": "Safety"},

                # Environment (B)
                {"code": "B1", "name": "Noise", "category": "Environment"},
                {"code": "B2", "name": "Environmental Protection", "category": "Environment"},
                {"code": "B3", "name": "Waste Management", "category": "Environment"},
                {"code": "B4", "name": "Dust Suppression & Emissions", "category": "Environment"},
                {"code": "B5", "name": "Air Emissions & Quality", "category": "Environment"},
                {"code": "B6", "name": "Flora & Fauna", "category": "Environment"},
                {"code": "B7", "name": "Soil Erosion", "category": "Environment"},
                {"code": "B8", "name": "Water Discharge / Contamination", "category": "Environment"},
                {"code": "B9", "name": "Groundwater Protection", "category": "Environment"},
                {"code": "B10", "name": "Flood Mitigation", "category": "Environment"},
                {"code": "B11", "name": "Sustainability", "category": "Environment"},

                # Health (C)
                {"code": "C1", "name": "Working in the Heat", "category": "Health"},
                {"code": "C2", "name": "Ergonomics", "category": "Health"},
                {"code": "C3", "name": "Occupational Health", "category": "Health"},
                {"code": "C4", "name": "Pest Control", "category": "Health"}
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
                {
                    "id": "PROJ-001",
                    "name": "Riyadh Metro Line 3",
                    "locations": ["Main Station", "Tunnel A", "Tunnel B", "Storage Yard"],
                    "responsiblePersons": [
                        {"name": "Eng. John", "phone": "+966 50 123 4567"},
                        {"name": "Supervisor Mike", "phone": "+966 50 234 5678"},
                        {"name": "Safety Officer Ali"}
                    ]
                },
                {
                    "id": "PROJ-002",
                    "name": "King Salman Park",
                    "locations": ["Visitor Center", "Landscape Zone A", "Construction Site B"],
                    "responsiblePersons": [
                        {"name": "Eng. Sarah", "phone": "+966 50 345 6789"},
                        {"name": "Manager David"}
                    ]
                },
                {
                    "id": "PROJ-003",
                    "name": "Red Sea Airport",
                    "locations": ["Terminal 1", "Runway", "ATC Tower"],
                    "responsiblePersons": [
                        {"name": "Eng. Ahmed", "phone": "+966 50 456 7890"},
                        {"name": "Supervisor Khaled", "phone": "+966 50 567 8901"}
                    ]
                },
                {
                    "id": "PROJ-004",
                    "name": "Diriyah Gate",
                    "locations": ["Heritage Site", "Museum", "Parking Area"],
                    "responsiblePersons": [
                        {"name": "Eng. Faisal"},
                        {"name": "Safety Manager Tom", "phone": "+966 50 678 9012"}
                    ]
                },
                {
                    "id": "PROJ-005",
                    "name": "NEOM The Line",
                    "locations": ["Module 42", "Spine Layer", "Logistics Hub"],
                    "responsiblePersons": [
                        {"name": "Director James", "phone": "+966 50 789 0123"},
                        {"name": "Lead Eng. Sam"}
                    ]
                }
            ]
        }
        return defaults.get(config_type.upper(), [])
