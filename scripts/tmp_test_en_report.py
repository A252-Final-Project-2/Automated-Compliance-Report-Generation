import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.module3.report_generator import generate_fast_report

sample_data = {
    "case_info": {"claim_id": "CL-123", "claim_amount": "RM 1,000", "generated_datetime": "25/05/2026 20:05:53"},
    "summary_stats": {"total_defects": 2, "completed_defects": 1, "pending_defects": 1, "critical_defects": 0, "overdue_defects": 1, "hda_non_compliant_defects": 0},
    "defect_list": [
        {"defect_id": "D-1", "description": "Cracked tile", "unit": "A-101", "reported_date": "01/05/2026", "deadline": "10/05/2026", "actual_completion_date": "15/05/2026", "status": "Completed", "overdue": "No", "hda_compliance_30_days": "Yes", "priority": "High", "remarks": ""},
        {"defect_id": "D-2", "description": "Leaking pipe", "unit": "A-101", "reported_date": "05/05/2026", "deadline": "20/05/2026", "actual_completion_date": "-", "status": "Pending", "overdue": "Yes", "hda_compliance_30_days": "No", "priority": "Normal", "remarks": ""},
    ]
}

print(generate_fast_report('Homeowner', sample_data, language='en'))
