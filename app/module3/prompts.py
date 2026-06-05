# prompts.py
import json


# =================================================
# LANGUAGE CONFIGURATIONS
# =================================================
LANGUAGE_CONFIG = {
    "ms": {
        "name": "Bahasa Malaysia",
        "system_instruction": (
            "Anda menjana laporan sokongan untuk Tribunal Tuntutan Pengguna Malaysia. "
            "Gunakan Bahasa Malaysia formal dan berkecuali sahaja; jangan campurkan Bahasa Inggeris. "
            "Jangan menambah fakta baharu, jangan membuat kesimpulan undang-undang, "
            "dan jangan menentukan liabiliti atau kesalahan mana-mana pihak."
        ),
        "ai_title": "LAPORAN RINGKASAN TUNTUTAN DIJANA AI",
        "report_title": "Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
        "generated_label": "Tarikh Jana",
        "disclaimer_title": "PENAFIAN AI:",
        "disclaimer_text": (
            "Laporan ini dijana dengan bantuan kecerdasan buatan (AI) bagi tujuan "
            "penyusunan dan ringkasan maklumat sahaja. Semua fakta, data dan bukti "
            "adalah berdasarkan rekod yang dikemukakan. Laporan ini tidak "
            "merupakan nasihat undang-undang dan tidak menggantikan penentuan "
            "atau keputusan Tribunal."
        )
    },
    "en": {
        "name": "English",
        "system_instruction": (
            "You are generating a support report for the Malaysia Consumer Claims Tribunal. "
            "Use formal and neutral English only; do not include Malay text. "
            "Do not add new facts, do not make legal conclusions, "
            "and do not determine liability or fault of any party."
        ),
        "ai_title": "AI-GENERATED CLAIM SUMMARY REPORT",
        "report_title": "TRIBUNAL SUPPORT REPORT – DEFECT LIABILITY PERIOD (DLP)",
        "generated_label": "Generated Date",
        "disclaimer_title": "AI DISCLAIMER:",
        "disclaimer_text": (
            "This report is generated with the assistance of artificial intelligence (AI) "
            "for the purpose of organising and summarising information based on records submitted. "
            "This report is provided to present information in a clear and neutral manner regarding the reported defects "
            "and should not be construed as legal advice. The AI system bears no responsibility for any action taken "
            "based on this report, and this report does not replace the determination or decision of the Tribunal."
        )
    }
}


def _translate_defect_list(defects_source, include_remarks=False):
    translated_defects = []

    for d in defects_source or []:
        if isinstance(d, str):
            d = {"description": d}
        elif not isinstance(d, dict):
            d = {}

        defect_obj = {
            "defect_id": d.get("defect_id", ""),
            "unit": d.get("unit", ""),
            "description": d.get("description", ""),
            "reported_date": d.get("reported_date", ""),
            "status": d.get("status", ""),
            "deadline": d.get("deadline", ""),
            "actual_completion_date": d.get("actual_completion_date", "-"),
            "days_to_complete": d.get("days_to_complete", "-"),
            "overdue": d.get("overdue", "No"),
            "hda_compliance_30_days": (
                "Complied with 30-Day Requirement under HDA"
                if d.get("hda_compliance_30_days") == "Yes"
                else "Failed to Comply with 30-Day Requirement under HDA"
            ),
            "priority": d.get("priority", "")
        }

        if include_remarks:
            defect_obj["remarks"] = d.get("remarks", "")

        translated_defects.append(defect_obj)

    return translated_defects

def translate_report_data_to_en(report_data, include_remarks=False):
    """
    Convert Malay report_data structure to English structure.
    include_remarks=True only for Homeowner role.
    """
    
    # Case Info
    case_info = report_data.get("case_info", {})
    case_info_en = {
        "tribunal": "Malaysia Consumer Claims Tribunal",
        "state": case_info.get("state_name", ""),
        "claim_number": case_info.get("claim_number", ""),
        "generated_date": case_info.get("generated_date", ""),
        "claim_amount": case_info.get("claim_amount", ""),
        "document": "Form 1 Supporting Document"
    }

    # Statistics
    stats = report_data.get("summary_stats", {})
    stats_en = {
        "total_defects": stats.get("total_defects", 0),
        "pending": stats.get("pending_defects", 0),
        "completed": stats.get("completed_defects", 0),
        "critical": stats.get("critical_defects", 0)
    }

    defects = report_data.get("defect_list", [])
    if not isinstance(defects, list):
        defects = []
    defects_en = _translate_defect_list(defects, include_remarks=include_remarks)

    return case_info_en, stats_en, defects_en

# =================================================
# HOMEOWNER PROMPT (BILINGUAL)
# =================================================
def homeowner_prompt(report_data, language="ms"):

    if language == "en":

        case_info_en, stats_en, defects_en = translate_report_data_to_en(
            report_data,
            include_remarks=True
        )

        return f"""
This support report is prepared to support the claim submitted by
the Claimant to the Malaysia Consumer Claims Tribunal (TTPM)
in relation to the Defect Liability Period (DLP).

IMPORTANT INSTRUCTIONS (MUST BE COMPLIED WITH):
1. Use formal administrative English and the writing style of an official Tribunal report.
2. Use passive, objective, and factual sentence structures throughout the report.
3. All statements must be framed strictly based on the records, information, and documents submitted.
4. Do not add any new facts, estimates, assumptions, inferences, or interpretations.
5. Do not make any legal conclusions, assessments of liability, or determinations of fault against any party.
6. Avoid the use of emotional language, personal narratives, or argumentative statements.
7. Use formal Tribunal-style phrases such as:
   - “based on the records submitted”
   - “as reported”
   - “for the purpose of the Tribunal’s consideration”
8. Ensure all defect descriptions, statuses, and remarks are written in formal English.
9. Where specific information is unavailable, clearly state:
   “No further information is recorded.”
10. Do not use any markdown formatting, emphasis symbols, or decorative text.
11. Ensure the report is structured, consistent, and reflects the tone of an official administrative document.

Case Information:
{json.dumps(case_info_en, indent=2, ensure_ascii=False)}

Statistics Summary:
{json.dumps(stats_en, indent=2, ensure_ascii=False)}

Defect List:
{json.dumps(defects_en, indent=2, ensure_ascii=False)}

Write the report with the following format:

Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)

1. Purpose of Report
[State that this report is prepared to summarise and present defect records for the Tribunal's consideration.]

2. Overview of Recorded Defects
[State the total number of defects, the number completed, those outstanding, and any critical items.]

3. Detailed Defect Information
[List each defect as follows:

a. Defect ID [defect_id]:
   Description: [description]
   Unit: [unit]
   Reported Date: [reported_date]
   Scheduled Completion Date: [deadline]
   Actual Completion Date: [actual_completion_date]
   Days to Complete: [days_to_complete] (include ONLY if Status is Completed)
   Status: [status]
   Overdue Status: [overdue]
   HDA Compliance (30 Days): [hda_compliance_30_days]
   Priority: [priority]
   Remarks: [remarks]

b. Defect ID [defect_id]:
...
]

4. Observations on Compliance and Deadlines
[Objectively state:
- Whether any defects have exceeded the scheduled completion date.
- Whether any defects are recorded as non-compliant with the 30-day HDA requirement.
Do not attribute responsibility.]

5. Formal Request from the Claimant
[State the relief or request submitted for Tribunal consideration.]

6. Conclusion
[The conclusion shall be drafted in a neutral and formal manner, stating that
this support report is prepared solely to summarise and present information
relating to defects reported during the Defect Liability Period (DLP),
based on the records submitted by the Claimant,
for the purpose of reference and consideration by the Malaysia Consumer Claims Tribunal,
without making any determination of fault, liability, or legal decision.]


AI Disclaimer:
This report was generated with the assistance of an artificial intelligence (AI) system
for the purpose of organising and summarising information based on records submitted
by the Claimant. This report is provided solely to present information in a clear
and neutral manner and does not constitute legal advice. The AI system bears no
responsibility for any action taken based on this report, and this report does not
replace or affect the determination or decision of the Malaysia Consumer Claims Tribunal.
""".strip()
    
    # Default: Bahasa Malaysia
    return f"""
Laporan sokongan ini disediakan bagi menyokong tuntutan yang dikemukakan oleh
Pihak Yang Menuntut kepada Tribunal Tuntutan Pengguna Malaysia (TTPM)
berhubung Tempoh Liabiliti Kecacatan (Defect Liability Period – DLP).

ARAHAN PENTING (WAJIB DIPATUHI):
1. Gunakan Bahasa Malaysia formal pentadbiran dan gaya penulisan laporan rasmi Tribunal.
2. Gunakan ayat pasif, objektif, dan berfakta sepanjang laporan.
3. Semua pernyataan hendaklah dirangka berdasarkan rekod, maklumat, dan dokumen yang dikemukakan sahaja.
4. Jangan menambah sebarang fakta baharu, anggaran, inferens, atau andaian.
5. Jangan membuat sebarang kesimpulan undang-undang, penilaian liabiliti, atau penentuan kesalahan mana-mana pihak.
6. Elakkan penggunaan bahasa bersifat emosi, naratif peribadi, atau hujahan.
7. Gunakan istilah seperti:
   - “berdasarkan rekod yang dikemukakan”
   - “seperti yang dilaporkan”
   - “untuk tujuan pertimbangan Tribunal”
8. Pastikan teks ULASAN dipaparkan dalam bahasa yang sama dengan bahasa laporan.
9. Jika maklumat tertentu tidak tersedia, nyatakan secara jelas:
   “Tiada maklumat lanjut direkodkan.”
10. Jangan gunakan sebarang format markdown, simbol penegasan, atau hiasan teks.
11. Susun ayat secara kemas, konsisten, dan menyerupai laporan pentadbiran rasmi.
Laporan hendaklah ditulis seolah-olah ia akan difailkan sebagai
dokumen sokongan rasmi kepada Tribunal Tuntutan Pengguna Malaysia.
12. Jika ulasan tidak diberikan atau hanya menyatakan ketiadaan tindakan, nyatakan secara ringkas dan neutral.

Maklumat Kes:
{json.dumps(report_data.get("case_info", {}), indent=2, ensure_ascii=False)}

Ringkasan Statistik:
{json.dumps(report_data.get("summary_stats", {}), indent=2, ensure_ascii=False)}

Senarai Kecacatan:
{json.dumps(report_data.get("defect_list", []), indent=2, ensure_ascii=False)}

Tulis laporan dengan format berikut:

Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)

1. Tujuan Laporan
[Nyatakan laporan ini disediakan bagi merumuskan dan membentangkan rekod kecacatan untuk pertimbangan Tribunal.]

2. Gambaran Keseluruhan Kecacatan Direkodkan
[Nyatakan jumlah kecacatan, jumlah yang telah diselesaikan, yang masih tertunggak dan sebarang perkara kritikal.]

3. Butiran Terperinci Kecacatan
[Senaraikan setiap kecacatan seperti berikut:

a. Kecacatan ID [defect_id]:
   Keterangan: [description]
   Unit: [unit]
   Tarikh Dilaporkan: [reported_date]
   Tarikh Siap Dijadualkan: [deadline]
   Tarikh Siap Sebenar: [actual_completion_date]
    Tempoh Siap (Hari): [days_to_complete] (paparkan HANYA jika Status ialah Telah Diselesaikan)
   Status: [status]
   Status Tertunggak: [overdue]
   Pematuhan HDA (30 Hari): [hda_compliance_30_days]
   Keutamaan: [priority]
   Ulasan: [remarks]

b. ID Kecacatan [defect_id]
...]

4. Pemerhatian Berkaitan Pematuhan dan Tarikh Akhir
[Nyatakan secara objektif:
- Jika terdapat kecacatan yang melepasi tarikh siap dijadualkan.
- Jika terdapat kecacatan yang tidak mematuhi tempoh 30 hari di bawah HDA.
Tanpa mengaitkan kesalahan atau tanggungjawab mana-mana pihak.]

5. Permohonan Rasmi Pihak Yang Menuntut
[Nyatakan permohonan rasmi kepada Tribunal]

6. Penutup
[Penutup hendaklah dirangka secara neutral dan formal dengan menyatakan bahawa
laporan sokongan ini disediakan semata-mata untuk merumuskan dan
mempersembahkan maklumat berkaitan kecacatan yang telah dilaporkan
sepanjang Tempoh Liabiliti Kecacatan (Defect Liability Period),
berdasarkan rekod yang dikemukakan oleh Pihak Yang Menuntut,
untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia,
tanpa membuat sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang.]


PENAFIAN AI:
Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan oleh Pihak Yang Menuntut. Laporan ini disediakan untuk memberikan maklumat yang jelas dan berkecuali mengenai kecacatan yang dilaporkan dan tidak boleh dianggap sebagai nasihat undang-undang. Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.
""".strip()


# =================================================
# DEVELOPER PROMPT (BILINGUAL)
# =================================================
def developer_prompt(report_data, language="ms"):
    if language == "en":
        case_info_en, stats_en, defects_en = translate_report_data_to_en(
            report_data,
            include_remarks=False
        )
        claimant_unit = report_data.get("claimant_unit", "")
        claimant_defects_en = _translate_defect_list(report_data.get("claimant_defect_list", []))
        other_defects_en = _translate_defect_list(report_data.get("other_defect_list", []))
        
        return f"""
This report is prepared by the Respondent (Developer) for compliance purposes
and as a reference document for the Malaysia Consumer Claims Tribunal (TTPM).

IMPORTANT INSTRUCTIONS (MUST BE COMPLIED WITH):
1. Use formal administrative English and the writing style of an official Tribunal report.
2. Use passive, objective, and factual sentence structures throughout the report.
3. Avoid the use of personal narratives, conversational language, or argumentative statements.
4. Ensure all defect descriptions are written in formal English
   (e.g. “Wall crack in master bedroom”, “Broken tile in bathroom”,
   “Leaking pipe under kitchen sink”, “Faulty electrical wiring in living room”,
   “Balcony sliding door stuck”, “Ceiling water stain near air-conditioner”).
5. Ensure all defect statuses are written consistently in English
   (Pending, In Progress, Completed, Delayed).
6. Do not add any new facts, assumptions, estimates, or explanations beyond the records provided.
7. Do not make any admission of liability, fault, or legal responsibility.
8. Do not use any markdown formatting, emphasis symbols, or decorative text.
9. Ensure the report is neatly structured, professional, and reflects the tone of an official administrative document.
10. When listing or discussing defects, separate the records under the headings
    "Claimant Owner Defect List" and "Other Owner Defect List in Case" where applicable.

The report shall be written as though it is intended to be filed as
an official compliance document before the Malaysia Consumer Claims Tribunal.

Claimant Owner Details:
{claimant_unit or "No claimant unit recorded."}

Case Information:
{json.dumps(case_info_en, indent=2, ensure_ascii=False)}

Statistics Summary:
{json.dumps(stats_en, indent=2, ensure_ascii=False)}

Claimant Owner Defect List:
{json.dumps(claimant_defects_en, indent=2, ensure_ascii=False)}

Other Owner Defect List in Case:
{json.dumps(other_defects_en, indent=2, ensure_ascii=False)}

Write the report in English with these NUMBERED sections (you MUST include the numbers):

Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)

1. Purpose of Report
[State that this report is prepared to present the current status of rectification works undertaken during the Defect Liability Period.]

2. Overview of Rectification Status
[Summarise:
- Total recorded defects
- Number completed
- Number outstanding
- Any recorded overdue matters
- Any records reflecting non-compliance with the 30-day HDA timeframe]

3. Completed Rectification Works
[List defects recorded as completed using the following structure:

a. Defect ID [defect_id]
   Description: [description]
   Unit: [unit]
   Reported Date: [reported_date]
   Scheduled Completion Date: [deadline]
   Actual Completion Date: [actual_completion_date]
    Days to Complete: [days_to_complete] (include ONLY for Completed defects)
   HDA Compliance (30 Days): [hda_compliance_30_days]

b. Defect ID [defect_id]
...]

4. Outstanding or Delayed Rectification Works
[List defects not recorded as completed using the following structure:

a. Defect ID [defect_id]
   Description: [description]
   Unit: [unit]
   Reported Date: [reported_date]
   Scheduled Completion Date: [deadline]
   Actual Completion Date: [actual_completion_date]
   Current Status: [status]
   Overdue Status: [overdue]
   HDA Compliance (30 Days): [hda_compliance_30_days]

b. Defect ID [defect_id]
...]

5. Observations on Timeframe Compliance
[State objectively the observations regarding timeframe compliance
based on the records submitted. Where relevant, indicate whether there
are defects that have exceeded the scheduled completion date or do not
comply with the thirty (30) day timeframe under the Housing Development
Act (HDA).

The observations should be summarised strictly based on the information
recorded and must not attribute fault or responsibility to any party.]

6. Developer’s Commitment Statement
[Briefly state the developer’s commitment to continue carrying out
rectification works for defects that are still recorded as unresolved
based on the information available in the records.]

7. Conclusion
[State that this compliance report summarises the status of rectification works during the Defect Liability Period,
based strictly on internal records,
for the purpose of Tribunal reference and consideration,
without any admission of fault, liability, or legal responsibility.]


AI Disclaimer:
This report was generated with the assistance of an artificial intelligence (AI) system
for the purpose of organising and summarising information based on records provided.
This report is intended solely to present information in a clear and neutral manner
and does not constitute legal advice. The AI system bears no responsibility for any
action taken based on this report, and this report does not replace or affect the
determination or decision of the Malaysia Consumer Claims Tribunal.
""".strip()
    
    # Default: Bahasa Malaysia
    claimant_unit = report_data.get("claimant_unit", "")
    claimant_defects = report_data.get("claimant_defect_list", [])
    other_defects = report_data.get("other_defect_list", [])

    return f"""
Laporan ini disediakan oleh Penentang (Pemaju) bagi tujuan pematuhan
dan sebagai dokumen rujukan kepada Tribunal Tuntutan Pengguna Malaysia (TTPM).

ARAHAN PENTING (WAJIB DIPATUHI):
1. Gunakan Bahasa Malaysia formal pentadbiran dan gaya penulisan laporan rasmi Tribunal.
2. Gunakan ayat pasif, objektif, dan berfakta sepanjang laporan.
3. Elakkan penggunaan bahasa berbentuk naratif peribadi, perbualan, atau hujahan.
4. Pastikan semua keterangan kecacatan dinyatakan dalam Bahasa Malaysia formal
   (contoh: Keretakan dinding di bilik tidur utama, Jubin pecah di bilik air,
   Paip bocor di bawah sinki dapur, Pendawaian elektrik rosak di ruang tamu,
   Pintu gelongsor balkoni tersangkut, Kesan tompokan air pada siling berhampiran penyaman udara).
5. Pastikan semua status kecacatan dinyatakan secara konsisten
   (Belum Selesai, Dalam Proses, Selesai, Tertangguh).
6. Semua pernyataan hendaklah dirangka berdasarkan rekod dan maklumat yang tersedia sahaja.
7. Jangan menambah sebarang fakta baharu, anggaran, inferens, atau penjelasan di luar rekod.
8. Jangan membuat sebarang pengakuan kesalahan, liabiliti, atau tanggungjawab undang-undang.
9. Jangan gunakan sebarang format markdown, simbol penegasan, atau hiasan teks.
10. Pastikan laporan disusun secara kemas, konsisten, dan menyerupai dokumen pentadbiran rasmi.
11. Apabila menyenaraikan atau menghuraikan kecacatan, asingkan rekod di bawah tajuk
    "Senarai Kecacatan Pemilik Menuntut" dan "Senarai Kecacatan Pemilik Lain Dalam Kes" jika berkaitan.

Laporan ini hendaklah ditulis seolah-olah ia akan difailkan sebagai
dokumen pematuhan rasmi kepada Tribunal Tuntutan Pengguna Malaysia.

Maklumat Kes:
{json.dumps(report_data.get("case_info", {}), indent=2, ensure_ascii=False)}

Ringkasan Statistik:
{json.dumps(report_data.get("summary_stats", {}), indent=2, ensure_ascii=False)}

Maklumat Pemilik Menuntut:
{claimant_unit or "Tiada unit pemilik menuntut direkodkan."}

Senarai Kecacatan Pemilik Menuntut:
{json.dumps(claimant_defects, indent=2, ensure_ascii=False)}

Senarai Kecacatan Pemilik Lain Dalam Kes:
{json.dumps(other_defects, indent=2, ensure_ascii=False)}

Tulis laporan dengan format berikut:

Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)

1. Tujuan Laporan
[Nyatakan bahawa laporan ini disediakan untuk membentangkan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan.]

2. Gambaran Keseluruhan Status Pembaikan
[Nyatakan:
- Jumlah keseluruhan kecacatan
- Jumlah yang telah diselesaikan
- Jumlah yang masih tertunggak
- Jika terdapat kecacatan yang melepasi tarikh akhir
- Jika terdapat ketidakpatuhan tempoh 30 hari di bawah HDA]

3. Kerja Pembaikan yang Telah Diselesaikan
[Senaraikan seperti berikut:

a. ID Kecacatan [defect_id]
   Keterangan: [description]
   Unit: [unit]
   Tarikh Dilaporkan: [reported_date]
   Tarikh Siap Dijadualkan: [deadline]
   Tarikh Siap Sebenar: [actual_completion_date]
    Tempoh Siap (Hari): [days_to_complete] (paparkan HANYA untuk kecacatan yang Telah Diselesaikan)
   Pematuhan HDA (30 Hari): [hda_compliance_30_days]

b. ID Kecacatan [defect_id]
...]

4. Kerja Pembaikan yang Masih Tertunggak atau Tertunda
[Senaraikan seperti berikut:

a. ID Kecacatan [defect_id]
   Keterangan: [description]
   Unit: [unit]
   Tarikh Dilaporkan: [reported_date]
   Tarikh Siap Dijadualkan: [deadline]
   Tarikh Siap Sebenar: [actual_completion_date]
   Status Semasa: [status]
   Status Tertunggak: [overdue]
   Pematuhan HDA (30 Hari): [hda_compliance_30_days]

b. ID Kecacatan [defect_id]
...]

5. Pemerhatian Berkaitan Pematuhan Tempoh
[Nyatakan secara objektif pemerhatian berkaitan pematuhan tempoh berdasarkan
rekod yang dikemukakan. Jika berkaitan, nyatakan sama ada terdapat kecacatan
yang melepasi tarikh siap yang dijadualkan atau tidak mematuhi tempoh
tiga puluh (30) hari di bawah Akta Pemajuan Perumahan (HDA).
Pemerhatian hendaklah dirumuskan berdasarkan maklumat yang direkodkan sahaja
tanpa mengaitkan kesalahan atau tanggungjawab mana-mana pihak.]

6. Kenyataan Komitmen Pemaju
[Nyatakan secara ringkas komitmen pemaju untuk meneruskan pelaksanaan
kerja pembaikan terhadap kecacatan yang masih direkodkan sebagai
belum diselesaikan berdasarkan maklumat yang tersedia dalam rekod.]

7. Penutup
[Nyatakan bahawa laporan ini disediakan bagi merumuskan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan,
berdasarkan rekod dalaman yang tersedia,
untuk tujuan rujukan dan pertimbangan Tribunal,
tanpa sebarang pengakuan kesalahan, liabiliti atau tanggungjawab undang-undang.]

PENAFIAN AI:
Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI)
bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang tersedia.
Laporan ini disediakan semata-mata untuk menyampaikan maklumat secara jelas
dan berkecuali serta tidak boleh dianggap sebagai nasihat undang-undang.
Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil
berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan
atau keputusan Tribunal Tuntutan Pengguna Malaysia.
""".strip()


# =================================================
# LEGAL / TRIBUNAL PROMPT (BILINGUAL)
# =================================================
def legal_prompt(report_data, language="ms"):
    if language == "en":
        # Translate case info to English
        case_info_en, stats_en, defects_en = translate_report_data_to_en(
            report_data,
            include_remarks=False
        )
        claimant_unit = report_data.get("claimant_unit", "")
        claimant_defects_en = _translate_defect_list(report_data.get("claimant_defect_list", []))
        other_defects_en = _translate_defect_list(report_data.get("other_defect_list", []))
        
        return f"""
This report is prepared for the purpose of providing an objective and neutral
overview of the current level of compliance with the
Defect Liability Period (DLP),
for reference by the Malaysia Consumer Claims Tribunal,
based on the records and information submitted.

IMPORTANT INSTRUCTIONS (MUST BE COMPLIED WITH):
1. Use formal administrative English and the writing style of a Tribunal reference document.
2. Use passive, objective, concise, and factual sentence structures throughout the report.
3. Avoid the use of personal narratives, conversational language, or argumentative statements.
4. All statements must be strictly based on records, information, and documents submitted.
5. Do not add any new facts, estimates, assumptions, interpretations, or inferences.
6. Do not make any determination of fault, liability, or legal responsibility.
7. Do not make any legal conclusions, findings, or recommendations.
8. Do not use any markdown formatting, emphasis symbols, or decorative text.
9. Ensure the report is structured, consistent, and reflects the tone of an official administrative reference document.
10. When listing or discussing defects, separate the records under the headings
    "Claimant Owner Defect List" and "Other Owner Defect List in Case" where applicable.

This report shall be written as though it is intended to be filed as
an official reference document before the Malaysia Consumer Claims Tribunal.

Claimant Owner Details:
{claimant_unit or "No claimant unit recorded."}

Case Information:
{json.dumps(case_info_en, indent=2, ensure_ascii=False)}

Statistics Summary:
{json.dumps(stats_en, indent=2, ensure_ascii=False)}

Claimant Owner Defect List:
{json.dumps(claimant_defects_en, indent=2, ensure_ascii=False)}

Other Owner Defect List in Case:
{json.dumps(other_defects_en, indent=2, ensure_ascii=False)}

Write the report in English with these NUMBERED sections (you MUST include the numbers):

Overview Report on Defect Liability Period (DLP) Compliance

1. Case Background
[Briefly outline:
- Claim reference number
- Claim amount (if recorded)
- Total number of recorded defects
based strictly on submitted documentation.]

2. Statistical Position of Defect Records
[State objectively:
- Total recorded defects
- Number completed
- Number outstanding
- Number recorded as overdue (if any)
- Any record indicating non-compliance with the 30-day HDA timeframe
without interpretation.]

3. Recorded Status and Timeframe Observations
[Describe the observations objectively based on the records submitted
by referring to the following information for each defect:

- Reported Date
- Scheduled Completion Date
- Actual Completion Date (if recorded)
- Days to Complete (for records with status Completed only)
- Current Status
- Overdue Status
- HDA Compliance (30 Days)

The observations should summarise the patterns or conditions
recorded in the data, such as:

- the number of defects recorded as completed compared with those still in progress or pending;
- whether any defects have exceeded the scheduled completion date;
- whether any defects are recorded as overdue;
- whether the records indicate compliance or non-compliance with the thirty (30) day requirement under the HDA.

Where relevant, refer to the number of defects or the relevant defect
records based on the information available.

These observations must be presented strictly based on the recorded
information and are not intended to make any determination of fault,
responsibility, or liability of any party.]

4. Observations on Outstanding or Delayed Matters

[Provide a detailed and formal paragraph based strictly on the records submitted, describing whether any defects are recorded as having exceeded their scheduled completion dates or remain unresolved beyond the thirty (30) day reference period.

The observation shall include:
- reference to the current status of the defects;
- correlation with the reported date and scheduled completion date;
- a statement that such defects are recorded as outstanding, delayed, or still in progress beyond the prescribed timeframe.

The paragraph must be written in full sentences using formal legal-administrative language, maintaining an objective and neutral tone, and must not attribute fault, responsibility, or liability to any party.]

5. Notes for Tribunal Consideration
[Provide a comprehensive paragraph stating that the information presented in this report is based strictly on the documents, records, and information submitted by the relevant parties for the purpose of reference and consideration by the Malaysia Consumer Claims Tribunal. State that the report has been prepared in an objective manner to present a clear and structured overview of the current status of defects during the Defect Liability Period (DLP). Emphasise that the contents of this report are not intended to make any assessment, conclusion, or determination regarding fault, liability, or legal responsibility of any party.]

6. Summary
[Provide a comprehensive paragraph stating that this reference report is prepared to summarise the current position of compliance with the Defect Liability Period (DLP) based strictly on the records and information submitted. State that the report consolidates information relating to defect status, completion timelines, and compliance with the prescribed timeframe for the purpose of Tribunal reference and consideration. Emphasise that the report is presented in a neutral manner and does not contain any determination of fault, liability, or legal conclusion against any party.]

AI Disclaimer:
This reference report was generated with the assistance of an artificial intelligence (AI) system
for the purpose of organising and summarising information based on submitted records.
This report is provided solely for Tribunal reference and informational purposes
and does not constitute legal advice.
This report does not replace or affect the determination or decision
of the Malaysia Consumer Claims Tribunal.
""".strip()
    
    # Default: Bahasa Malaysia
    claimant_unit = report_data.get("claimant_unit", "")
    claimant_defects = report_data.get("claimant_defect_list", [])
    other_defects = report_data.get("other_defect_list", [])

    return f"""
Laporan ini disediakan bagi tujuan memberikan gambaran keseluruhan
secara objektif dan berkecuali berhubung tahap pematuhan
Tempoh Liabiliti Kecacatan (Defect Liability Period – DLP)
untuk rujukan Tribunal Tuntutan Pengguna Malaysia.

ARAHAN PENTING (WAJIB DIPATUHI):
1. Gunakan Bahasa Malaysia formal pentadbiran dan gaya penulisan laporan rasmi Tribunal.
2. Gunakan ayat pasif, objektif, dan berfakta sepanjang laporan.
3. Elakkan penggunaan bahasa berbentuk naratif peribadi, perbualan, atau hujahan.
4. Semua pernyataan hendaklah dirangka berdasarkan rekod, maklumat,
   dan dokumen yang dikemukakan sahaja.
5. Jangan menambah sebarang fakta baharu, anggaran, inferens,
   tafsiran, atau penjelasan di luar rekod yang tersedia.
6. Jangan membuat sebarang penentuan kesalahan, liabiliti,
   atau tanggungjawab undang-undang.
7. Jangan membuat sebarang kesimpulan atau syor undang-undang.
8. Jangan gunakan sebarang format markdown, simbol penegasan,
   atau hiasan teks.
9. Pastikan laporan disusun secara kemas, konsisten,
   dan menyerupai dokumen pentadbiran rasmi.
10. Apabila menyenaraikan atau menghuraikan kecacatan, asingkan rekod di bawah tajuk
    "Senarai Kecacatan Pemilik Menuntut" dan "Senarai Kecacatan Pemilik Lain Dalam Kes" jika berkaitan.

Laporan ini hendaklah ditulis seolah-olah ia akan difailkan sebagai
dokumen rujukan rasmi kepada Tribunal Tuntutan Pengguna Malaysia.

Maklumat Kes:
{json.dumps(report_data.get("case_info", {}), indent=2, ensure_ascii=False)}

Ringkasan Statistik:
{json.dumps(report_data.get("summary_stats", {}), indent=2, ensure_ascii=False)}

Maklumat Pemilik Menuntut:
{claimant_unit or "Tiada unit pemilik menuntut direkodkan."}

Senarai Kecacatan Pemilik Menuntut:
{json.dumps(claimant_defects, indent=2, ensure_ascii=False)}

Senarai Kecacatan Pemilik Lain Dalam Kes:
{json.dumps(other_defects, indent=2, ensure_ascii=False)}

Tulis laporan dengan format berikut:

Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)

1. Latar Belakang Kes
[Nyatakan secara ringkas:
- Nombor rujukan tuntutan
- Amaun tuntutan (jika direkodkan)
- Jumlah keseluruhan kecacatan yang direkodkan
berdasarkan dokumen yang dikemukakan.]

2. Kedudukan Statistik Rekod Kecacatan
[Nyatakan secara objektif:
- Jumlah keseluruhan kecacatan
- Jumlah yang telah diselesaikan
- Jumlah yang masih belum diselesaikan
- Jika terdapat kecacatan yang direkodkan sebagai tertunggak
- Jika terdapat rekod ketidakpatuhan tempoh 30 hari di bawah HDA
tanpa membuat tafsiran.]

3. Pemerhatian Berkaitan Status dan Tempoh
[Huraikan pemerhatian secara objektif berdasarkan rekod yang dikemukakan
dengan merujuk kepada maklumat berikut bagi setiap kecacatan:

- Tarikh Dilaporkan
- Tarikh Siap Dijadualkan
- Tarikh Siap Sebenar (jika direkodkan)
- Tempoh Siap (Hari) (hanya bagi rekod berstatus Telah Diselesaikan)
- Status Semasa
- Status Tertunggak
- Pematuhan tempoh tiga puluh (30) hari di bawah HDA

Pemerhatian hendaklah dirumuskan secara ringkas dengan mengenal pasti
keadaan atau pola yang direkodkan dalam data, contohnya:

- bilangan kecacatan yang telah diselesaikan berbanding yang masih dalam tindakan atau belum diselesaikan;
- kewujudan kecacatan yang melepasi tarikh siap dijadualkan;
- kewujudan kecacatan yang direkodkan sebagai tertunggak;
- rekod pematuhan atau ketidakpatuhan terhadap tempoh tiga puluh (30) hari di bawah HDA.

Jika berkaitan, nyatakan bilangan kecacatan atau rujuk kepada rekod
kecacatan yang berkaitan berdasarkan maklumat yang tersedia.

Pemerhatian ini hendaklah dibentangkan berdasarkan maklumat yang
direkodkan sahaja tanpa membuat sebarang penentuan kesalahan,
tanggungjawab, atau liabiliti mana-mana pihak.]

4. Pemerhatian Berkaitan Perkara Tertunggak atau Lewat
[Huraikan secara terperinci dan formal berdasarkan rekod yang dikemukakan sama ada terdapat kecacatan yang melepasi tarikh siap yang dijadualkan atau masih belum diselesaikan melebihi tempoh rujukan tiga puluh (30) hari.

Pemerhatian hendaklah merangkumi:
- rujukan kepada status semasa kecacatan;
- kaitan dengan tarikh pelaporan dan tarikh siap dijadualkan;
- kenyataan bahawa kecacatan tersebut direkodkan sebagai tertunggak atau masih dalam tindakan melebihi tempoh masa yang ditetapkan.

Gunakan ayat lengkap dalam bentuk perenggan dan kekalkan gaya bahasa formal serta berkecuali tanpa membuat sebarang penentuan kesalahan atau tanggungjawab mana-mana pihak.]

5. Nota Untuk Pertimbangan Tribunal
[Huraikan secara menyeluruh dalam bentuk perenggan bahawa maklumat yang dibentangkan dalam laporan ini adalah berdasarkan dokumen, rekod, dan maklumat yang telah dikemukakan oleh pihak-pihak berkaitan untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia. Nyatakan bahawa laporan ini disusun secara objektif bagi memberikan gambaran yang jelas dan teratur berhubung kedudukan semasa kecacatan sepanjang Tempoh Liabiliti Kecacatan (DLP). Tegaskan bahawa kandungan laporan ini tidak bertujuan untuk membuat sebarang penilaian, kesimpulan, atau penentuan berhubung kesalahan, liabiliti, atau tanggungjawab undang-undang mana-mana pihak.]

6. Rumusan
[Huraikan secara komprehensif dalam bentuk perenggan bahawa laporan rujukan ini disediakan bagi merumuskan kedudukan semasa pematuhan Tempoh Liabiliti Kecacatan (DLP) berdasarkan sepenuhnya kepada rekod dan maklumat yang dikemukakan. Nyatakan bahawa laporan ini menghimpunkan maklumat berkaitan status kecacatan, tempoh pelaksanaan, serta pematuhan terhadap garis masa yang ditetapkan untuk tujuan rujukan dan pertimbangan Tribunal. Tegaskan bahawa laporan ini disediakan secara berkecuali dan tidak mengandungi sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang terhadap mana-mana pihak.]

PENAFIAN AI
Laporan rujukan ini dijana dengan bantuan sistem kecerdasan buatan (AI)
bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan.
Laporan ini disediakan semata-mata untuk tujuan rujukan Tribunal
dan tidak boleh dianggap sebagai nasihat undang-undang.
Laporan ini tidak menggantikan penentuan atau keputusan
Tribunal Tuntutan Pengguna Malaysia.
""".strip()


# =================================================
# PROMPT SELECTOR (BILINGUAL SUPPORT)
# =================================================
def build_prompt(role, report_data, language="ms"):
    """
    Pemilih prompt berdasarkan peranan pengguna dan bahasa
    Select prompt based on user role and language
    
    Args:
        role: "Homeowner", "Developer", or "Legal"
        report_data: Dictionary containing case information
        language: "ms" for Bahasa Malaysia, "en" for English
    """
    if role == "Homeowner":
        return homeowner_prompt(report_data, language)
    elif role == "Developer":
        return developer_prompt(report_data, language)
    else:
        return legal_prompt(report_data, language)


def get_language_config(language="ms"):
    """
    Get language-specific configuration
    """
    return LANGUAGE_CONFIG.get(language, LANGUAGE_CONFIG["ms"])
