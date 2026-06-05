import importlib.util
import sys
from pathlib import Path

# Load report_generator module directly
spec = importlib.util.spec_from_file_location(
    "report_generator",
    str(Path(__file__).resolve().parents[1] / "app" / "module3" / "report_generator.py")
)
report_generator = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = report_generator
module_dir = Path(__file__).resolve().parents[1] / "app" / "module3"
# Ensure module dir is on sys.path so absolute imports in module work
sys.path.insert(0, str(module_dir))
spec.loader.exec_module(report_generator)

# Minimal sample data
report_data = {
    'case_info': {
        'claim_id': 'C-001',
        'claim_amount': '1000.00',
        'generated_datetime': '25 Mei 2026, 10:00'
    },
    'summary_stats': {
        'total_defects': 1,
        'completed_defects': 0,
        'pending_defects': 1,
        'critical_defects': 0,
        'overdue_defects': 0,
        'hda_non_compliant_defects': 0,
    },
    'defect_list': [
        {
            'defect_id': 'D-1',
            'unit': 'Suite 12-08',
            'description': 'Cracked tile in kitchen',
            'reported_date': '01-05-2026',
            'deadline': '01-06-2026',
            'actual_completion_date': '-',
            'days_to_complete': '-',
            'status': 'Pending',
            'overdue': 'No',
            'hda_compliance_30_days': 'No',
            'priority': '',
            'remarks': ''
        }
    ]
}

print('--- generate_fast_report (ms, Homeowner) ---')
print(report_generator.generate_fast_report('Homeowner', report_data, language='ms'))

print('\n--- generate_ai_report (ms, Homeowner) [AI disabled fallback] ---')
print(report_generator.generate_ai_report('Homeowner', report_data, language='ms'))
