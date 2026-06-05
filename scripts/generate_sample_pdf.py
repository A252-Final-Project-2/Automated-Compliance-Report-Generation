from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.module3.report_generator import generate_fast_report, _format_generated_datetime
from app.module3.prompts import LANGUAGE_CONFIG

out = os.path.join(os.path.dirname(__file__), 'sample_en_report.pdf')
report_text = generate_fast_report('Developer', {
    'case_info': {'claim_id': 'TTPM/TEST/2026/0001','claim_amount':'RM 1,234.00','generated_datetime': _format_generated_datetime('en')},
    'summary_stats': {'total_defects':2,'completed_defects':1,'pending_defects':1,'critical_defects':0,'overdue_defects':1,'hda_non_compliant_defects':0},
    'defect_list':[]
}, language='en')

lang_conf = LANGUAGE_CONFIG.get('en')
ai_title = lang_conf.get('ai_title')
report_title = lang_conf.get('report_title')
generated_label = lang_conf.get('generated_label')
subtitle = "Overview Report on Defect Liability Period (DLP) Compliance"

c = canvas.Canvas(out, pagesize=A4)
width, height = A4
left_margin = 50
y = height - 100

# AI title centered
# AI title centered (larger bold)
c.setFont('Helvetica-Bold', 16)
ai_w = c.stringWidth(ai_title, 'Helvetica-Bold', 16)
c.drawString((width - ai_w) / 2, y, ai_title)
y -= 20

# Tribunal title centered (bold, smaller)
c.setFont('Helvetica-Bold', 12)
rpt_w = c.stringWidth(report_title, 'Helvetica-Bold', 12)
c.drawString((width - rpt_w) / 2, y, report_title)
y -= 16

# Generated date left (normal)
c.setFont('Helvetica', 10)
date_line = f"{generated_label}: {_format_generated_datetime('en')}"
c.drawString(left_margin, y, date_line)
y -= 16

# Subtitle centered (bold)
c.setFont('Helvetica-Bold', 11)
sub_w = c.stringWidth(subtitle, 'Helvetica-Bold', 11)
c.drawString((width - sub_w) / 2, y, subtitle)
y -= 22

# Body text
c.setFont('Helvetica', 10)
text_obj = c.beginText(left_margin, y)
for line in report_text.split('\n'):
    text_obj.textLine(line)
c.drawText(text_obj)

c.showPage()
c.save()
print('Wrote', out)
