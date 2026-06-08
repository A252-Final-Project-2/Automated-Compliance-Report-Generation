import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

try:
    from .config_mappings import STATUS_TRANSLATION
    from .groqai_client import get_ai_client
    from .legal_metadata import get_legal_manager
    from .prompts import build_prompt, get_language_config
except ImportError:  # pragma: no cover - fallback for direct execution from module3/
    from config_mappings import STATUS_TRANSLATION
    from groqai_client import get_ai_client
    from legal_metadata import get_legal_manager
    from prompts import build_prompt, get_language_config


FAST_REPORT_LABELS = {
    "ms": {
        "report_title": "LAPORAN SOKONGAN TRIBUNAL – TEMPOH LIABILITI KECACATAN (DLP)",
        "generated_at": "Tarikh Jana",
        "claim_summary": "Ringkasan Tuntutan",
        "defect_id": "Kecacatan ID",
        "description": "Keterangan",
        "unit": "Unit",
        "reported_date": "Tarikh Dilaporkan",
        "scheduled_completion_date": "Tarikh Siap Dijadualkan",
        "actual_completion_date": "Tarikh Siap Sebenar",
        "days_to_complete": "Tempoh Siap (Hari)",
        "status": "Status",
        "current_status": "Status Semasa",
        "overdue_status": "Status Tertunggak",
        "hda_compliance": "Status Pematuhan HDA",
        "priority": "Keutamaan",
        "remarks": "Ulasan",
        "homeowner_report_subtitle": "Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
        "homeowner_purpose_text": "Laporan ini disediakan bagi merumuskan dan membentangkan rekod kecacatan untuk pertimbangan Tribunal Tuntutan Pengguna Malaysia (TTPM) berhubung dengan tuntutan yang dikemukakan oleh Pihak Yang Menuntut.",
        "homeowner_overview_text_empty": "Berdasarkan rekod yang dikemukakan, tiada kecacatan yang dilaporkan sepanjang Tempoh Liabiliti Kecacatan (Defect Liability Period). Jumlah kecacatan yang dilaporkan adalah 0, dan tidak terdapat kecacatan yang masih tertunggak atau kritikal.",
        "homeowner_overview_text": "Berdasarkan rekod yang dikemukakan, jumlah kecacatan yang dilaporkan adalah {total}. Daripada jumlah ini, {completed} telah diselesaikan, {pending} masih tertunggak, dan {critical} dikategorikan sebagai kritikal.",
        "no_defects_text": "Tiada kecacatan yang dilaporkan untuk tujuan pertimbangan Tribunal.",
        "purpose": "Tujuan Laporan",
        "case_information": "Maklumat Kes",
        "summary": "Ringkasan Statistik",
        "defect_details": "Butiran Kecacatan",
        "observations": "Pemerhatian Berkaitan Pematuhan dan Tarikh Akhir",
        "statement": "Permohonan / Kenyataan",
        "conclusion": "Penutup",
        "homeowner_observations_text_empty": "Tiada kecacatan yang melepasi tarikh siap dijadualkan atau tidak mematuhi tempoh 30 hari di bawah HDA, kerana tiada kecacatan yang dilaporkan.",
        "homeowner_observations_text": "Berdasarkan rekod yang dikemukakan, {overdue_count} kecacatan telah melepasi tarikh siap dijadualkan, dan {hda_non_compliant_count} kecacatan tidak mematuhi tempoh 30 hari di bawah HDA.",
        "homeowner_request_text": "Pihak Yang Menuntut telah mengemukakan tuntutan kepada Tribunal Tuntutan Pengguna Malaysia dengan jumlah tuntutan sebanyak {claim_amount}, berhubung dengan {item_service} yang dilakukan pada tarikh {transaction_date}.",
        "ai_disclaimer_title": "PENAFIAN AI:",
        "ai_disclaimer_text": "Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan oleh Pihak Yang Menuntut. Laporan ini disediakan untuk memberikan maklumat yang jelas dan berkecuali mengenai kecacatan yang dilaporkan dan tidak boleh dianggap sebagai nasihat undang-undang. Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
        "developer_report_subtitle": "Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
        "developer_purpose_text": "Laporan ini disediakan untuk membentangkan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan (DLP) berdasarkan rekod dalaman pemaju.",
        "developer_overview_text": "Jumlah kecacatan yang direkodkan adalah {total}. Daripada jumlah ini, {completed} telah diselesaikan dan {pending} masih tertunggak. Terdapat {overdue} kecacatan yang melepasi tarikh akhir yang dijadualkan dan {hda_non_compliant} kecacatan yang tidak mematuhi tempoh 30 hari di bawah HDA.",
        "completed_works_title": "3. Kerja Pembaikan yang Telah Diselesaikan",
        "no_completed_defects_text": "Tiada kecacatan yang telah diselesaikan direkodkan.",
        "pending_works_title": "4. Kerja Pembaikan yang Masih Tertunggak atau Tertunda",
        "no_pending_defects_text": "Tiada kecacatan yang masih tertunggak atau tertunda.",
        "developer_observations_text": "Berdasarkan rekod yang dikemukakan, {overdue} kecacatan telah melepasi tarikh siap yang dijadualkan, dan {hda_non_compliant} kecacatan tidak mematuhi tempoh tiga puluh (30) hari di bawah Akta Pemajuan Perumahan (HDA).",
        "developer_commitment_text": "Pemaju berkomitmen untuk meneruskan pelaksanaan kerja pembaikan terhadap kecacatan yang masih direkodkan sebagai belum diselesaikan berdasarkan maklumat yang tersedia dalam rekod.",
        "developer_ai_disclaimer_text": "Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang tersedia. Laporan ini disediakan semata-mata untuk menyampaikan maklumat secara jelas dan berkecuali serta tidak boleh dianggap sebagai nasihat undang-undang. Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
        "legal_report_subtitle": "Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)",
        "legal_case_background_text": "Nombor rujukan tuntutan: {claim_id}. Amaun tuntutan: {claim_amount}. Jumlah keseluruhan kecacatan yang direkodkan: {total_defects}.",
        "legal_stats_position_text": "Jumlah keseluruhan kecacatan: {total}. Telah diselesaikan: {completed}. Masih belum diselesaikan: {pending}. Direkodkan sebagai tertunggak: {overdue}. Tidak mematuhi tempoh 30 hari HDA: {hda_non_compliant}.",
        "legal_status_observations_text": "Berdasarkan rekod yang dikemukakan, {total} kecacatan telah direkodkan. Daripada jumlah ini, {completed} telah diselesaikan dan {pending} masih dalam tindakan. Terdapat {overdue} kecacatan yang melepasi tarikh siap yang dijadualkan dan {hda_non_compliant} kecacatan yang tidak mematuhi tempoh 30 hari di bawah HDA.",
        "legal_outstanding_observations_text": "Berdasarkan rekod yang dikemukakan, {overdue} kecacatan telah melepasi tarikh siap yang dijadualkan dan masih belum diselesaikan. Kecacatan-kecacatan ini direkodkan sebagai tertunggak atau masih dalam tindakan melebihi tempoh masa yang ditetapkan.",
        "legal_notes_text": "Maklumat yang dibentangkan dalam laporan ini adalah berdasarkan dokumen, rekod, dan maklumat yang telah dikemukakan oleh pihak-pihak berkaitan untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia. Laporan ini disusun secara objektif bagi memberikan gambaran yang jelas dan teratur berhubung kedudukan semasa kecacatan sepanjang Tempoh Liabiliti Kecacatan (DLP). Kandungan laporan ini tidak bertujuan untuk membuat sebarang penilaian, kesimpulan, atau penentuan berhubung kesalahan, liabiliti, atau tanggungjawab undang-undang mana-mana pihak.",
        "legal_summary_text": "Laporan rujukan ini disediakan bagi merumuskan kedudukan semasa pematuhan Tempoh Liabiliti Kecacatan (DLP) berdasarkan sepenuhnya kepada rekod dan maklumat yang dikemukakan. Laporan ini menghimpunkan maklumat berkaitan status kecacatan, tempoh pelaksanaan, serta pematuhan terhadap garis masa yang ditetapkan untuk tujuan rujukan dan pertimbangan Tribunal. Laporan ini disediakan secara berkecuali dan tidak mengandungi sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang terhadap mana-mana pihak.",
        "legal_ai_disclaimer_text": "Laporan rujukan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan. Laporan ini disediakan semata-mata untuk tujuan rujukan Tribunal dan tidak boleh dianggap sebagai nasihat undang-undang. Laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
        "remarks_placeholder": "Tiada ulasan dikemukakan",
        "overdue_yes": "Tertunggak",
        "overdue_no": "Tidak Tertunggak",
        "hda_yes": "Mematuhi",
        "hda_no": "Tidak Mematuhi",
        "hda_pending": "Tidak Mematuhi",
        "completed": "Telah Diselesaikan",
        "pending": "Belum Diselesaikan",
        "in_progress": "Dalam Tindakan",
        "delayed": "Tertangguh",
        "closed": "Ditutup",
        "request_homeowner": "Laporan ini disediakan untuk tujuan rujukan Tribunal berdasarkan rekod yang dikemukakan.",
        "request_developer": "Pemaju hendaklah meneruskan kerja pembaikan bagi kecacatan yang masih belum diselesaikan berdasarkan rekod yang ada.",
        "request_legal": "Laporan ini disediakan untuk rujukan dan pertimbangan Tribunal berdasarkan rekod yang dikemukakan.",
        "request_admin": "Laporan ini disediakan untuk rujukan pentadbiran dan pertimbangan Tribunal.",
        "conclusion_homeowner": "Laporan sokongan ini disediakan semata-mata untuk merumuskan dan mempersembahkan maklumat berkaitan kecacatan sepanjang Tempoh Liabiliti Kecacatan berdasarkan rekod yang dikemukakan, untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia, tanpa membuat sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang.",
        "conclusion_developer": "Laporan pematuhan ini merumuskan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan berdasarkan rekod dalaman, untuk rujukan dan pertimbangan Tribunal, tanpa pengakuan kesalahan, liabiliti, atau tanggungjawab undang-undang.",
        "conclusion_legal": "Laporan sokongan ini disediakan untuk rujukan dan pertimbangan Tribunal berdasarkan rekod yang dikemukakan, tanpa penentuan kesalahan, liabiliti, atau keputusan undang-undang.",
        "conclusion_admin": "Laporan ini disediakan sebagai ringkasan pentadbiran berdasarkan rekod yang tersedia untuk rujukan Tribunal.",
        "defects_section": "Senarai Kecacatan",
    },
    "en": {
        "report_title": "TRIBUNAL SUPPORT REPORT – DEFECT LIABILITY PERIOD (DLP)",
        "generated_at": "Generated Date",
        "claim_summary": "Claim Summary",
        "defect_id": "Defect ID",
        "description": "Description",
        "unit": "Unit",
        "reported_date": "Reported Date",
        "scheduled_completion_date": "Scheduled Completion Date",
        "actual_completion_date": "Actual Completion Date",
        "days_to_complete": "Days to Complete",
        "status": "Status",
        "current_status": "Current Status",
        "overdue_status": "Overdue Status",
        "hda_compliance": "HDA Compliance Status",
        "priority": "Priority",
        "remarks": "Remarks",
        "homeowner_report_subtitle": "Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)",
        "homeowner_purpose_text": "This report is prepared to summarise and present defect records for the consideration of the Malaysia Consumer Claims Tribunal (TTPM) in relation to the claim submitted by the Claimant.",
        "homeowner_overview_text_empty": "Based on the records submitted, no defects have been reported during the Defect Liability Period (DLP). The total number of defects reported is 0, and there are no defects that are outstanding or critical.",
        "homeowner_overview_text": "Based on the records submitted, the total number of defects reported is {total}. Of this number, {completed} have been completed, {pending} are still outstanding, and {critical} are categorized as critical.",
        "no_defects_text": "No defects have been reported for the purpose of Tribunal consideration.",
        "purpose": "Purpose of Report",
        "case_information": "Case Information",
        "summary": "Summary Statistics",
        "defect_details": "Defect Details",
        "observations": "Observations on Compliance and Deadlines",
        "statement": "Request / Statement",
        "conclusion": "Conclusion",
        "homeowner_observations_text_empty": "No defects have exceeded the scheduled completion date or failed to comply with the 30-day HDA requirement, as no defects have been reported.",
        "homeowner_observations_text": "Based on the records submitted, {overdue_count} defects have exceeded their scheduled completion dates, and {hda_non_compliant_count} defects do not comply with the 30-day requirement under the HDA.",
        "homeowner_request_text": "The Claimant has submitted a claim to the Malaysia Consumer Claims Tribunal for the amount of {claim_amount}, in relation to {item_service} carried out on {transaction_date}.",
        "ai_disclaimer_title": "AI DISCLAIMER:",
        "ai_disclaimer_text": "This report is generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on records submitted by the Claimant. This report is provided to present information in a clear and neutral manner regarding the reported defects and should not be construed as legal advice. The AI system bears no responsibility for any action taken based on this report, and this report does not replace the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "ai_disclaimer_text_old": "This report was generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on records submitted by the Claimant. This report is provided to present information in a clear and neutral manner and should not be construed as legal advice. The AI system bears no responsibility for any action taken based on this report, and this report does not replace the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "developer_report_subtitle": "Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)",
        "developer_purpose_text": "This report is prepared to present the current status of rectification works undertaken during the Defect Liability Period (DLP) based on internal developer records.",
        "developer_overview_text": "The total number of recorded defects is {total}. Of this number, {completed} have been completed and {pending} are still outstanding. There are {overdue} defects that have exceeded the scheduled completion date and {hda_non_compliant} defects that do not comply with the 30-day requirement under the HDA.",
        "completed_works_title": "3. Completed Rectification Works",
        "no_completed_defects_text": "No completed defects are recorded.",
        "pending_works_title": "4. Outstanding or Delayed Rectification Works",
        "no_pending_defects_text": "No outstanding or delayed defects are recorded.",
        "developer_observations_text": "Based on the records submitted, {overdue} defects have exceeded their scheduled completion dates, and {hda_non_compliant} defects do not comply with the thirty (30) day requirement under the Housing Development Act (HDA).",
        "developer_commitment_text": "The developer is committed to continue carrying out rectification works for defects that are still recorded as unresolved based on the information available in the records.",
        "developer_ai_disclaimer_text": "This report is generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on available records. This report is provided solely to present information in a clear and neutral manner and should not be construed as legal advice. The AI system bears no responsibility for any action taken based on this report, and this report does not replace the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "developer_ai_disclaimer_text_old": "This report was generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on available records. This report is intended solely to present information in a clear and neutral manner and does not constitute legal advice. The AI system bears no responsibility for any action taken based on this report, and this report does not replace the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "legal_report_subtitle": "Overview Report on Defect Liability Period (DLP) Compliance",
        "legal_case_background_text": "Claim reference number: {claim_id}. Claim amount: {claim_amount}. Total number of recorded defects: {total_defects}.",
        "legal_stats_position_text": "Total recorded defects: {total}. Completed: {completed}. Still unresolved: {pending}. Recorded as overdue: {overdue}. Non-compliant with 30-day HDA requirement: {hda_non_compliant}.",
        "legal_status_observations_text": "Based on the records submitted, {total} defects have been recorded. Of this number, {completed} have been completed and {pending} are still in progress. There are {overdue} defects that have exceeded their scheduled completion dates and {hda_non_compliant} defects that do not comply with the 30-day requirement under the HDA.",
        "legal_outstanding_observations_text": "Based on the records submitted, {overdue} defects have exceeded their scheduled completion dates and remain unresolved. These defects are recorded as outstanding, delayed, or still in progress beyond the prescribed timeframe.",
        "legal_notes_text": "The information presented in this report is based strictly on the documents, records, and information submitted by the relevant parties for the purpose of reference and consideration by the Malaysia Consumer Claims Tribunal. This report has been prepared in an objective manner to present a clear and structured overview of the current status of defects during the Defect Liability Period (DLP). The contents of this report are not intended to make any assessment, conclusion, or determination regarding fault, liability, or legal responsibility of any party.",
        "legal_summary_text": "This reference report is prepared to summarise the current position of compliance with the Defect Liability Period (DLP) based strictly on the records and information submitted. This report consolidates information relating to defect status, completion timelines, and compliance with the prescribed timeframe for the purpose of Tribunal reference and consideration. The report is presented in a neutral manner and does not contain any determination of fault, liability, or legal conclusion against any party.",
        "legal_ai_disclaimer_text": "This reference report is generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on submitted records. This report is provided solely for Tribunal reference purposes and should not be construed as legal advice. This report does not replace the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "legal_ai_disclaimer_text_old": "This reference report was generated with the assistance of an artificial intelligence (AI) system for the purpose of organising and summarising information based on submitted records. This report is provided solely for Tribunal reference and informational purposes and does not constitute legal advice. This report does not replace or affect the determination or decision of the Malaysia Consumer Claims Tribunal.",
        "remarks_placeholder": "No remarks recorded",
        "overdue_yes": "Overdue",
        "overdue_no": "Not Overdue",
        "hda_yes": "Compliant",
        "hda_no": "Non-Compliant",
        "hda_pending": "Non-Compliant",
        "completed": "Completed",
        "pending": "Pending",
        "in_progress": "In Progress",
        "delayed": "Delayed",
        "closed": "Closed",
        "request_homeowner": "This report is prepared for Tribunal reference based on the submitted records.",
        "request_developer": "The developer should continue rectification works for unresolved defects based on the available records.",
        "request_legal": "This report is prepared for reference and consideration by the Tribunal based on the submitted records.",
        "request_admin": "This report is prepared for administrative reference and Tribunal consideration.",
        "conclusion_homeowner": "This support report is prepared solely to summarise and present information relating to defects during the Defect Liability Period, based on the submitted records, for reference and consideration by the Malaysia Consumer Claims Tribunal, without making any determination of fault, liability, or legal decision.",
        "conclusion_developer": "This compliance report summarises rectification status during the Defect Liability Period based on internal records, for Tribunal reference and consideration, without admission of fault, liability, or legal responsibility.",
        "conclusion_legal": "This support report is prepared for Tribunal reference and consideration based on the submitted records, without any determination of fault, liability, or legal decision.",
        "conclusion_admin": "This report is prepared as an administrative summary based on the available records for Tribunal reference.",
        "defects_section": "Defect List",
    },
}


def _now_app_timezone():
    app_timezone = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
    try:
        return datetime.now(ZoneInfo(app_timezone))
    except Exception:
        if app_timezone == "Asia/Kuala_Lumpur":
            return datetime.now(timezone.utc) + timedelta(hours=8)
        return datetime.now(timezone.utc)


def _format_generated_datetime(language):
    now = _now_app_timezone()
    if language == "ms":
        month_names = {
            1: "Januari", 2: "Februari", 3: "Mac", 4: "April",
            5: "Mei", 6: "Jun", 7: "Julai", 8: "Ogos",
            9: "September", 10: "Oktober", 11: "November", 12: "Disember",
        }
        return f"{now.day:02d} {month_names[now.month]} {now.year}, {now.strftime('%H:%M')}"
    return now.strftime("%d %B %Y, %H:%M")


def _format_display_date(value, language):
    text = _fast_text(value, "-").strip()
    if not text or text in {"-", "N/A", "None"}:
        return "-"

    date_part = text[:10]
    parsed = None
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(date_part, date_format)
            break
        except Exception:
            continue

    if not parsed:
        return text

    if language == "ms":
        month_names = {
            1: "Januari", 2: "Februari", 3: "Mac", 4: "April",
            5: "Mei", 6: "Jun", 7: "Julai", 8: "Ogos",
            9: "September", 10: "Oktober", 11: "November", 12: "Disember",
        }
        return f"{parsed.day:02d} {month_names[parsed.month]} {parsed.year}"

    return parsed.strftime("%d %B %Y")


def refresh_generated_datetime_line(report_text, language):
    return (report_text or "").strip()


def _normalise_unit_for_grouping(value):
    text = str(value or "").strip().lower()
    if not text:
        return ""

    unit_match = re.search(r"\b[a-z]{1,4}-\d{1,4}(?:-\d{1,4})?\b", text, flags=re.IGNORECASE)
    if unit_match:
        return unit_match.group(0).lower()

    text = re.sub(r"^\s*unit\s+", "", text, flags=re.IGNORECASE)
    text = text.split(",", 1)[0]
    return re.sub(r"\s+", "", text)


def split_defects_by_claimant(claimant_unit, defects):
    claimant_unit_normalized = _normalise_unit_for_grouping(claimant_unit)
    claimant_defects = []
    other_defects = []

    for defect in defects or []:
        if isinstance(defect, str):
            defect = {"description": defect}
        elif not isinstance(defect, dict):
            defect = {}

        defect_unit = _normalise_unit_for_grouping(defect.get("unit", ""))
        if claimant_unit_normalized and defect_unit == claimant_unit_normalized:
            claimant_defects.append(defect)
        else:
            other_defects.append(defect)

    return claimant_defects, other_defects


def _extract_claimant_unit(report_data):
    claimant = report_data.get("claimant", {}) or {}
    case_info = report_data.get("case_info", {}) or {}
    claimant_unit = claimant.get("address_line_1") or claimant.get("unit")
    if not claimant_unit:
        claimant_unit = case_info.get("claimant_unit") or case_info.get("unit")
    return claimant_unit or ""


def _prepare_role_specific_defect_groups(report_data, role):
    if role not in ("Developer", "Legal"):
        return report_data

    prepared = dict(report_data)
    claimant_unit = _extract_claimant_unit(prepared)
    claimant_defects, other_defects = split_defects_by_claimant(
        claimant_unit,
        prepared.get("defect_list", []),
    )

    prepared["claimant_unit"] = claimant_unit
    prepared["claimant_defect_list"] = claimant_defects
    prepared["other_defect_list"] = other_defects
    prepared["all_defect_list"] = prepared.get("defect_list", [])
    return prepared


def _fast_label(language, key):
    return FAST_REPORT_LABELS.get(language, FAST_REPORT_LABELS["ms"]).get(key, key)


def _ensure_disclaimer_localized(text, language):
    """Normalize any English 'AI DISCLAIMER' headings to the localized label."""
    if not text:
        return text
    # Prepare a normalized localized heading: single colon + newline
    localized = _fast_label(language, "ai_disclaimer_title") or "PENAFIAN AI:"
    localized = str(localized).strip()
    # remove any trailing colons/spaces and ensure single ':'
    localized = localized.rstrip(':').rstrip() + ':'
    # ensure newline after the colon so heading is on its own line
    if not localized.endswith(':\n'):
        localized = localized[:-1] + ':\n'

    out = text
    # Replace common English variants (with any trailing colons/spaces/newlines)
    out = re.sub(r"AI\s*DISCLAIMER[:\s]*", localized, out, flags=re.IGNORECASE)
    out = re.sub(r"AI\s*Disclaimer[:\s]*", localized, out, flags=re.IGNORECASE)

    # Also collapse any accidental repeated colons after existing localized heading
    # e.g., 'AI DISCLAIMER:::::' -> 'AI DISCLAIMER:\n'
    out = re.sub(r"(AI\s*DISCLAIMER)[:]{2,}", lambda m: (m.group(1) + ':\n'), out, flags=re.IGNORECASE)

    return out


def _fast_text(value, fallback="-"):
    text = str(value if value is not None else fallback).strip()
    return text if text else fallback


def _status_label(status, language):
    if language == "ms":
        return STATUS_TRANSLATION.get("ms", {}).get(status, status)
    return STATUS_TRANSLATION.get("en", {}).get(status, status)


def _bool_label(value, language):
    truthy = str(value).strip().lower() in {"yes", "ya", "true", "1"}
    labels = FAST_REPORT_LABELS.get(language, FAST_REPORT_LABELS["ms"])
    return labels["overdue_yes"] if truthy else labels["overdue_no"]


def _hda_compliance_label(value, language, status=None):
    normalized = str(value).strip().lower()
    truthy = normalized in {"yes", "ya", "true", "1", "mematuhi", "compliant"}
    labels = FAST_REPORT_LABELS.get(language, FAST_REPORT_LABELS["ms"])
    return labels["hda_yes"] if truthy else labels["hda_no"]


# Hardcoded remarks translations (Malay -> English)
HARDCODED_REMARKS = {
    "belum siap dibaiki": "Not repaired yet",
    "belum siap": "Not completed yet",
    "jubin yang rosak masih belum dibaiki": "The cracked tile has not been repaired yet",
    "jubin rosak": "Cracked tile",
    "Pintu gelongsor tersekat": "Sliding door stuck",
    "belum diperbaiki": "Not repaired",
    "masih dalam proses": "Still in progress",
    "menunggu bahan": "Awaiting materials",
    "kontraktor tidak tersedia": "Contractor unavailable",
    "dijadualkan semula": "Rescheduled",
}

def _translate(text, language, role, label):
    """Translates text, falling back to original if translation fails."""
    if not text or not isinstance(text, str) or not text.strip() or text.strip() == "-":
        return text
    
    text_stripped = text.strip()
    
    # Check hardcoded remarks translations first
    if label == "defect_remark" and language == "en" and text_stripped in HARDCODED_REMARKS:
        return HARDCODED_REMARKS[text_stripped]
    
    try:
        try:
            # Use the function designed for individual fields
            from .ai_translate_cached import translate_text_cached
        except (ImportError, ModuleNotFoundError):
            from ai_translate_cached import translate_text_cached
        result = translate_text_cached(text, language=language, label=label, role=role)
        
        # Hardcoded translation fixes for English
        if language == "en":
            result = result.replace("mailbox", "tile").replace("Mailbox", "Tile")
        
        return result
    except Exception as e:
        raise e


def _format_defect_block(defect, index, language, role):
    lines = []
    number_label = "Kecacatan ID" if language == "ms" else "Defect ID"
    description_label = "Keterangan" if language == "ms" else "Description"
    reported_label = "Tarikh Dilaporkan" if language == "ms" else "Reported Date"
    scheduled_label = "Tarikh Siap Dijadualkan" if language == "ms" else "Scheduled Completion Date"
    actual_label = "Tarikh Siap Sebenar" if language == "ms" else "Actual Completion Date"
    status_label = "Status" if language == "ms" else "Status"
    overdue_label = "Status Tertunggak" if language == "ms" else "Overdue Status"
    hda_label = "Status Pematuhan HDA" if language == "ms" else "HDA Compliance Status"
    priority_label = "Keutamaan" if language == "ms" else "Priority"
    remarks_label = "Ulasan" if language == "ms" else "Remarks"

    lines.append(f"{chr(96 + index)}. {number_label} {_fast_text(defect.get('defect_id'))}:")
    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
    lines.append(f"   {description_label}: {description}")
    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
    lines.append(f"   {reported_label}: {_format_display_date(defect.get('reported_date'), language)}")
    lines.append(f"   {scheduled_label}: {_format_display_date(defect.get('deadline'), language)}")
    lines.append(f"   {actual_label}: {_format_display_date(defect.get('actual_completion_date'), language)}")

    status_value = _status_label(_fast_text(defect.get("status"), ""), language)
    if status_value == _fast_label(language, "completed"):
        days_label = "Tempoh Siap (Hari)" if language == "ms" else "Days to Complete"
        lines.append(f"   {days_label}: {_fast_text(defect.get('days_to_complete'))}")

    lines.append(f"   {status_label}: {status_value}")
    lines.append(f"   {overdue_label}: {_bool_label(defect.get('overdue'), language)}")
    lines.append(f"   {hda_label}: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
    lines.append(f"   {priority_label}: {_fast_text(defect.get('priority'), 'Normal')}")

    if role == "Homeowner":
        remarks_text = _fast_text(defect.get("remarks"), "")
        if remarks_text:
            remarks = _translate(remarks_text, language, role, "defect_remark")
        else:
            remarks = _fast_label(language, "remarks_placeholder")
        lines.append(f"   {remarks_label}: {remarks}")

    return "\n".join(lines)


def generate_fast_report(role, report_data, language="ms"):
    """
    Generate report in exact format matching tribunal requirements
    All content in single language (BM or EN, no mixing)
    """
    report_data = _prepare_role_specific_defect_groups(report_data, role)
    labels = FAST_REPORT_LABELS.get(language, FAST_REPORT_LABELS["ms"])
    case_info = report_data.get("case_info", {}) or {}
    stats = report_data.get("summary_stats", {}) or {}
    defects = report_data.get("defect_list", []) or []
    

    # Report title and header: AI title (English), tribunal title, generated timestamp, and localized subtitle
    gen_dt = case_info.get("generated_datetime") or _format_generated_datetime(language)
    report_title_line = labels.get("report_title", "LAPORAN SOKONGAN TRIBUNAL – TEMPOH LIABILITI KECACATAN (DLP)")
    generated_label = labels.get('generated_at', 'Tarikh Jana')

    lines = []
    if language == 'en':
        try:
            lang_conf = get_language_config(language)
            ai_title = lang_conf.get('ai_title') or 'AI-GENERATED CLAIM SUMMARY REPORT'
        except Exception:
            ai_title = 'AI-GENERATED CLAIM SUMMARY REPORT'
        lines.append(ai_title)
        lines.append("")
        lines.append(report_title_line)
        lines.append(f"{generated_label}: {_fast_text(gen_dt)}")
        lines.append("")
        # (English subtitle is added later in the role-specific English branch to avoid duplication)
    else:
        lines = [
            report_title_line,
            f"{generated_label}: {_fast_text(gen_dt)}",
            "",
        ]

    total = int(stats.get("total_defects", 0) or 0)
    completed = int(stats.get("completed_defects", 0) or 0)
    pending = int(stats.get("pending_defects", 0) or 0)
    critical = int(stats.get("critical_defects", 0) or 0)
    overdue_count = int(stats.get("overdue_defects", 0) or 0)
    hda_non_compliant_count = int(stats.get("hda_non_compliant_defects", 0) or 0)
    closed_count = int(stats.get("closed_defects", 0) or 0)

    def add_defect_list(section_defects):
        if not section_defects:
            lines.append(labels["no_defects_text"])
            return
        for index, defect in enumerate(section_defects, 1):
            lines.extend(["", _format_defect_block(defect, index, language, role)])

    if language == "ms":
        if role == "Homeowner":
            lines.append(labels["homeowner_report_subtitle"])
            lines.extend(["", f"1. {labels['purpose']}", labels["homeowner_purpose_text"]])
            lines.extend(["", f"2. {labels['summary']}"])
            lines.append(labels["homeowner_overview_text_empty"] if total == 0 else labels["homeowner_overview_text"].format(total=total, completed=completed, pending=pending, critical=critical))
            lines.extend(["", f"3. {labels['defect_details']}"])
            add_defect_list(defects)
            lines.extend(["", f"4. {labels['observations']}"])
            lines.append(labels["homeowner_observations_text_empty"] if total == 0 else labels["homeowner_observations_text"].format(overdue_count=overdue_count, hda_non_compliant_count=hda_non_compliant_count))
            lines.extend([
                "",
                "5. Permohonan Rasmi Pihak Yang Menuntut",
                labels["homeowner_request_text"].format(
                    claim_amount=_fast_text(case_info.get("claim_amount")),
                    item_service=_fast_text(case_info.get("item_service")),
                    transaction_date=_format_display_date(case_info.get("transaction_date"), language),
                ),
                "",
                f"6. {labels['conclusion']}",
                labels["conclusion_homeowner"],
                "",
                labels["ai_disclaimer_title"],
                labels["ai_disclaimer_text"],
            ])
        elif role == "Developer":
            completed_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) == labels["completed"]]
            pending_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) != labels["completed"]]
            lines.append(labels["developer_report_subtitle"])
            lines.extend(["", f"1. {labels['purpose']}", labels["developer_purpose_text"]])
            lines.extend(["", "2. Gambaran Keseluruhan Status Pembaikan"])
            lines.append(labels["developer_overview_text"].format(total=total, completed=completed, pending=pending, overdue=overdue_count, hda_non_compliant=hda_non_compliant_count))
            lines.extend(["", labels["completed_works_title"]])
            add_defect_list(completed_defects)
            lines.extend(["", labels["pending_works_title"]])
            add_defect_list(pending_defects)
            lines.extend([
                "",
                "5. Pemerhatian Berkaitan Pematuhan Tempoh",
                labels["developer_observations_text"].format(overdue=overdue_count, hda_non_compliant=hda_non_compliant_count),
                "",
                "6. Kenyataan Komitmen Pemaju",
                labels["developer_commitment_text"],
                "",
                f"7. {labels['conclusion']}",
                labels["conclusion_developer"],
                "",
                labels["ai_disclaimer_title"],
                labels["developer_ai_disclaimer_text"],
            ])
        else:
            lines.append(labels["legal_report_subtitle"])
            lines.extend([
                "",
                "1. Latar Belakang Kes",
                labels["legal_case_background_text"].format(claim_id=_fast_text(case_info.get("claim_id")), claim_amount=_fast_text(case_info.get("claim_amount")), total_defects=total),
                "",
                "2. Kedudukan Statistik Rekod Kecacatan",
                f"Jumlah keseluruhan kecacatan: {total}",
                f"Telah diselesaikan: {completed}",
                f"Kes Ditutup: {closed_count}",
                f"Masih belum diselesaikan: {pending}",
                f"Direkodkan sebagai tertunggak: {overdue_count}",
                f"Tidak mematuhi tempoh 30 hari HDA: {hda_non_compliant_count}",
                "",
                "3. Pemerhatian Berkaitan Status dan Tempoh",
                labels["legal_status_observations_text"].format(total=total, completed=completed, pending=pending, overdue=overdue_count, hda_non_compliant=hda_non_compliant_count),
                "",
                "4. Pemerhatian Berkaitan Perkara Tertunggak atau Lewat",
                labels["legal_outstanding_observations_text"].format(overdue=overdue_count),
                "",
                "5. Nota Untuk Pertimbangan Tribunal",
                labels["legal_notes_text"],
                "",
                "6. Rumusan",
                labels["legal_summary_text"],
                "",
                labels["ai_disclaimer_title"],
                labels["legal_ai_disclaimer_text"],
            ])
        out = "\n".join(lines).strip()
        out = _ensure_disclaimer_localized(out, language)
        return out

    if role == "Homeowner":
        lines.append(labels["homeowner_report_subtitle"])
        lines.extend(["", f"1. {labels['purpose']}", labels["homeowner_purpose_text"]])
        lines.extend(["", "2. Overview of Recorded Defects"])
        lines.append(labels["homeowner_overview_text_empty"] if total == 0 else labels["homeowner_overview_text"].format(total=total, completed=completed, pending=pending, critical=critical))
        lines.extend(["", "3. Detailed Defect Information"])
        add_defect_list(defects)
        lines.extend(["", f"4. {labels['observations']}"])
        lines.append(labels["homeowner_observations_text_empty"] if total == 0 else labels["homeowner_observations_text"].format(overdue_count=overdue_count, hda_non_compliant_count=hda_non_compliant_count))
        lines.extend([
            "",
            "5. Formal Request from the Claimant",
            labels["homeowner_request_text"].format(
                claim_amount=_fast_text(case_info.get("claim_amount")),
                item_service=_fast_text(case_info.get("item_service")),
                transaction_date=_format_display_date(case_info.get("transaction_date"), language),
            ),
            "",
            f"6. {labels['conclusion']}",
            labels["conclusion_homeowner"],
            "",
            labels["ai_disclaimer_title"],
            labels["ai_disclaimer_text"],
        ])
    elif role == "Developer":
        completed_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) == labels["completed"]]
        pending_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) != labels["completed"]]
        lines.extend(["", f"1. {labels['purpose']}", labels["developer_purpose_text"]])
        lines.extend(["", "2. Overview of Rectification Status"])
        lines.append(labels["developer_overview_text"].format(total=total, completed=completed, pending=pending, overdue=overdue_count, hda_non_compliant=hda_non_compliant_count))
        lines.extend(["", labels["completed_works_title"]])
        add_defect_list(completed_defects)
        lines.extend(["", labels["pending_works_title"]])
        add_defect_list(pending_defects)
        lines.extend([
            "",
            "5. Observations on Timeframe Compliance",
            labels["developer_observations_text"].format(overdue=overdue_count, hda_non_compliant=hda_non_compliant_count),
            "",
            "6. Developer's Commitment Statement",
            labels["developer_commitment_text"],
            "",
            f"7. {labels['conclusion']}",
            labels["conclusion_developer"],
            "",
            labels["ai_disclaimer_title"],
            labels["developer_ai_disclaimer_text"],
        ])
    else:
        lines.append(labels["legal_report_subtitle"])
        lines.extend([
            "",
            "1. Case Background",
            labels["legal_case_background_text"].format(claim_id=_fast_text(case_info.get("claim_id")), claim_amount=_fast_text(case_info.get("claim_amount")), total_defects=total),
            "",
            "2. Statistical Position of Defect Records",
            f"Total recorded defects: {total}",
            f"Completed: {completed}",
            f"Closed Cases: {closed_count}",
            f"Still unresolved: {pending}",
            f"Recorded as overdue: {overdue_count}",
            f"Non-compliant with 30-day HDA requirement: {hda_non_compliant_count}",
            "",
            "3. Recorded Status and Timeframe Observations",
            labels["legal_status_observations_text"].format(total=total, completed=completed, pending=pending, overdue=overdue_count, hda_non_compliant=hda_non_compliant_count),
            "",
            "4. Observations on Outstanding or Delayed Matters",
            labels["legal_outstanding_observations_text"].format(overdue=overdue_count),
            "",
            "5. Notes for Tribunal Consideration",
            labels["legal_notes_text"],
            "",
            "6. Summary",
            labels["legal_summary_text"],
            "",
            labels["ai_disclaimer_title"],
            labels["legal_ai_disclaimer_text"],
        ])
    out = "\n".join(lines).strip()
    out = _ensure_disclaimer_localized(out, language)
    return out

    if role == "Homeowner":
        lines.append(labels["homeowner_report_subtitle"])
        lines.extend(["", f"1. {labels['purpose']}", labels["homeowner_purpose_text"]])
        lines.extend(["", f"2. {labels['summary']}"])

        if total == 0:
            lines.append(labels["homeowner_overview_text_empty"])
        else:
            lines.append(labels["homeowner_overview_text"].format(total=total, completed=completed, pending=pending, critical=critical))

        lines.extend(["", f"3. {labels['defect_details']}"])

        if defects:
            for index, defect in enumerate(defects, 1):
                defect_lines = [f"a. {labels['defect_id']} {_fast_text(defect.get('defect_id'))}:"]
                description = _translate(_fast_text(defect.get("description")), language, role, "defect_description")
                defect_lines.append(f"   {labels['description']}: {description}")
                defect_lines.append(f"   {labels['unit']}: {_fast_text(defect.get('unit'))}")
                defect_lines.append(f"   {labels['reported_date']}: {_format_display_date(defect.get('reported_date'), language)}")
                defect_lines.append(f"   {labels['scheduled_completion_date']}: {_format_display_date(defect.get('deadline'), language)}")
                defect_lines.append(f"   {labels['actual_completion_date']}: {_format_display_date(defect.get('actual_completion_date'), language)}")

                status_value = _status_label(_fast_text(defect.get("status"), ""), language)
                if status_value == labels["completed"]:
                    defect_lines.append(f"   {labels['days_to_complete']}: {_fast_text(defect.get('days_to_complete'))}")

                defect_lines.append(f"   {labels['status']}: {status_value}")
                defect_lines.append(f"   {labels['overdue_status']}: {_bool_label(defect.get('overdue'), language)}")
                defect_lines.append(f"   {labels['hda_compliance']}: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
                defect_lines.append(f"   {labels['priority']}: {_fast_text(defect.get('priority'), 'Normal')}")

                remarks_text = _fast_text(defect.get("remarks"), "")
                if remarks_text:
                    remarks = _translate(remarks_text, language, role, "defect_remark")
                else:
                    remarks = labels["remarks_placeholder"]
                defect_lines.append(f"   {labels['remarks']}: {remarks}")
                lines.extend(["", *defect_lines])
        else:
            lines.append(labels["no_defects_text"])

        lines.extend(["", f"4. {labels['observations']}"])

        if total == 0:
            lines.append(labels["homeowner_observations_text_empty"])
        else:
            lines.append(labels["homeowner_observations_text"].format(overdue_count=overdue_count, hda_non_compliant_count=hda_non_compliant_count))

        lines.extend([
            "",
        ])

        # Role-specific subtitles
        if role == "Homeowner":
            lines.append("Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)")
            lines.extend([
                "",
                "1. Tujuan Laporan",
                "Laporan ini disediakan bagi merumuskan dan membentangkan rekod kecacatan untuk pertimbangan Tribunal Tuntutan Pengguna Malaysia (TTPM) berhubung dengan tuntutan yang dikemukakan oleh Pihak Yang Menuntut.",
                "",
                "2. Gambaran Keseluruhan Kecacatan Direkodkan",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            critical = int(stats.get("critical_defects", 0) or 0)
            
            if total == 0:
                lines.append("Berdasarkan rekod yang dikemukakan, tiada kecacatan yang dilaporkan sepanjang Tempoh Liabiliti Kecacatan (Defect Liability Period). Jumlah kecacatan yang dilaporkan adalah 0, dan tidak terdapat kecacatan yang masih tertunggak atau kritikal.")
            else:
                lines.append(f"Berdasarkan rekod yang dikemukakan, jumlah kecacatan yang dilaporkan adalah {total}. Daripada jumlah ini, {completed} telah diselesaikan, {pending} masih tertunggak, dan {critical} dikategorikan sebagai kritikal.")
            
            lines.extend([
                "",
                "3. Butiran Terperinci Kecacatan",
            ])
            
            if defects:
                for index, defect in enumerate(defects, 1):
                    lines.append("")
                    lines.append(f"a. Kecacatan ID {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Keterangan: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Tarikh Dilaporkan: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Tarikh Siap Dijadualkan: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Tarikh Siap Sebenar: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    
                    status_value = _status_label(_fast_text(defect.get("status"), ""), language)
                    if status_value == _fast_label(language, "completed"):
                        lines.append(f"   Tempoh Siap (Hari): {_fast_text(defect.get('days_to_complete'))}")
                    
                    lines.append(f"   Status: {status_value}")
                    lines.append(f"   Status Tertunggak: {_bool_label(defect.get('overdue'), language)}")
                    lines.append(f"   Status Pematuhan HDA: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
                    lines.append(f"   Keutamaan: {_fast_text(defect.get('priority'), 'Normal')}")
                    remarks_text = _fast_text(defect.get("remarks"), "")
                    if remarks_text:
                        remarks = _translate(remarks_text, language, role, "defect_remark")
                    else:
                        remarks = _fast_label(language, "remarks_placeholder")
                    lines.append(f"   Ulasan: {remarks}")
            else:
                lines.append("Tiada kecacatan yang dilaporkan untuk tujuan pertimbangan Tribunal.")
            
            overdue_count = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant_count = int(stats.get("hda_non_compliant_defects", 0) or 0)
            
            lines.extend([
                "",
                "4. Pemerhatian Berkaitan Pematuhan dan Tarikh Akhir",
            ])
            
            if total == 0:
                lines.append("Tiada kecacatan yang melepasi tarikh siap dijadualkan atau tidak mematuhi tempoh 30 hari di bawah HDA, kerana tiada kecacatan yang dilaporkan.")
            else:
                lines.append(f"Berdasarkan rekod yang dikemukakan, {overdue_count} kecacatan telah melepasi tarikh siap dijadualkan, dan {hda_non_compliant_count} kecacatan tidak mematuhi tempoh 30 hari di bawah HDA.")
            
            lines.extend([
                "",
                "5. Permohonan Rasmi Pihak Yang Menuntut",
                f"Pihak Yang Menuntut telah mengemukakan tuntutan kepada Tribunal Tuntutan Pengguna Malaysia dengan jumlah tuntutan sebanyak {_fast_text(case_info.get('claim_amount'))}, berhubung dengan {_fast_text(case_info.get('item_service'))} yang dilakukan pada tarikh {_format_display_date(case_info.get('transaction_date'), language)}.",
                "",
                "6. Penutup",
                "Laporan sokongan ini disediakan semata-mata untuk merumuskan dan mempersembahkan maklumat berkaitan kecacatan yang telah dilaporkan sepanjang Tempoh Liabiliti Kecacatan (Defect Liability Period), berdasarkan rekod yang dikemukakan oleh Pihak Yang Menuntut, untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia, tanpa membuat sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang.",
                "",
                "PENAFIAN AI:",
                "Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan oleh Pihak Yang Menuntut. Laporan ini disediakan untuk memberikan maklumat yang jelas dan berkecuali mengenai kecacatan yang dilaporkan dan tidak boleh dianggap sebagai nasihat undang-undang. Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
            ])
        
        elif role == "Developer":
            lines.append("Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)")
            claimant_unit = report_data.get("claimant_unit", "")
            claimant_defects, other_defects = split_defects_by_claimant(
                claimant_unit,
                report_data.get("defect_list", [])
            )
            
            lines.extend([
                "",
                "1. Tujuan Laporan",
                "Laporan ini disediakan untuk membentangkan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan (DLP) berdasarkan rekod dalaman pemaju.",
                "",
                "2. Gambaran Keseluruhan Status Pembaikan",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            overdue = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant = int(stats.get("hda_non_compliant_defects", 0) or 0)
            
            lines.append(f"Jumlah kecacatan yang direkodkan adalah {total}. Daripada jumlah ini, {completed} telah diselesaikan dan {pending} masih tertunggak. Terdapat {overdue} kecacatan yang melepasi tarikh akhir yang dijadualkan dan {hda_non_compliant} kecacatan yang tidak mematuhi tempoh 30 hari di bawah HDA.")
            
            lines.extend([
                "",
                "3. Kerja Pembaikan yang Telah Diselesaikan",
            ])
            
            completed_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) in {_fast_label(language, "completed"), "Telah Diselesaikan"}]
            if completed_defects:
                for index, defect in enumerate(completed_defects, 1):
                    lines.append("")
                    lines.append(f"a. ID Kecacatan {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Keterangan: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Tarikh Dilaporkan: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Tarikh Siap Dijadualkan: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Tarikh Siap Sebenar: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    lines.append(f"   Tempoh Siap (Hari): {_fast_text(defect.get('days_to_complete'))}")
                    lines.append(f"   Status Pematuhan HDA: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
            else:
                lines.append("Tiada kecacatan yang telah diselesaikan direkodkan.")
            
            lines.extend([
                "",
                "4. Kerja Pembaikan yang Masih Tertunggak atau Tertunda",
            ])
            
            pending_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) not in {_fast_label(language, "completed"), "Telah Diselesaikan"}]
            if pending_defects:
                for index, defect in enumerate(pending_defects, 1):
                    lines.append("")
                    lines.append(f"a. ID Kecacatan {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Keterangan: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Tarikh Dilaporkan: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Tarikh Siap Dijadualkan: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Tarikh Siap Sebenar: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    status_value = _status_label(_fast_text(defect.get("status"), ""), language)
                    lines.append(f"   Status Semasa: {status_value}")
                    lines.append(f"   Status Tertunggak: {_bool_label(defect.get('overdue'), language)}")
                    lines.append(f"   Status Pematuhan HDA: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
            else:
                lines.append("Tiada kecacatan yang masih tertunggak atau tertunda.")
            
            lines.extend([
                "",
                "5. Pemerhatian Berkaitan Pematuhan Tempoh",
                f"Berdasarkan rekod yang dikemukakan, {overdue} kecacatan telah melepasi tarikh siap yang dijadualkan, dan {hda_non_compliant} kecacatan tidak mematuhi tempoh tiga puluh (30) hari di bawah Akta Pemajuan Perumahan (HDA).",
                "",
                "6. Kenyataan Komitmen Pemaju",
                "Pemaju berkomitmen untuk meneruskan pelaksanaan kerja pembaikan terhadap kecacatan yang masih direkodkan sebagai belum diselesaikan berdasarkan maklumat yang tersedia dalam rekod.",
                "",
                "7. Penutup",
                "Laporan ini disediakan bagi merumuskan status kerja pembaikan sepanjang Tempoh Liabiliti Kecacatan berdasarkan rekod dalaman yang tersedia, untuk tujuan rujukan dan pertimbangan Tribunal, tanpa sebarang pengakuan kesalahan, liabiliti atau tanggungjawab undang-undang.",
                "",
                "PENAFIAN AI:",
                "Laporan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang tersedia. Laporan ini disediakan semata-mata untuk menyampaikan maklumat secara jelas dan berkecuali serta tidak boleh dianggap sebagai nasihat undang-undang. Sistem AI tidak bertanggungjawab terhadap sebarang tindakan yang diambil berdasarkan laporan ini dan laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
            ])
        
        else:  # Legal role
            lines.append("Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)")
            
            lines.extend([
                "",
                "1. Latar Belakang Kes",
                f"Nombor rujukan tuntutan: {_fast_text(case_info.get('claim_id'))}. Amaun tuntutan: {_fast_text(case_info.get('claim_amount'))}. Jumlah keseluruhan kecacatan yang direkodkan: {_fast_text(stats.get('total_defects'))}.",
                "",
                "2. Kedudukan Statistik Rekod Kecacatan",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            overdue = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant = int(stats.get("hda_non_compliant_defects", 0) or 0)
            closed = int(stats.get("closed_defects", 0) or 0)
            
            lines.extend([
                f"Jumlah keseluruhan kecacatan: {total}",
                f"Telah diselesaikan: {completed}",
                f"Kes Ditutup: {closed}",
                f"Masih belum diselesaikan: {pending}",
                f"Direkodkan sebagai tertunggak: {overdue}",
                f"Tidak mematuhi tempoh 30 hari HDA: {hda_non_compliant}",
            ])
            
            lines.extend([
                "",
                "3. Pemerhatian Berkaitan Status dan Tempoh",
                f"Berdasarkan rekod yang dikemukakan, {total} kecacatan telah direkodkan. Daripada jumlah ini, {completed} telah diselesaikan dan {pending} masih dalam tindakan. Terdapat {overdue} kecacatan yang melepasi tarikh siap yang dijadualkan dan {hda_non_compliant} kecacatan yang tidak mematuhi tempoh 30 hari di bawah HDA.",
                "",
                "4. Pemerhatian Berkaitan Perkara Tertunggak atau Lewat",
                f"Berdasarkan rekod yang dikemukakan, {overdue} kecacatan telah melepasi tarikh siap yang dijadualkan dan masih belum diselesaikan. Kecacatan-kecacatan ini direkodkan sebagai tertunggak atau masih dalam tindakan melebihi tempoh masa yang ditetapkan.",
                "",
                "5. Nota Untuk Pertimbangan Tribunal",
                "Maklumat yang dibentangkan dalam laporan ini adalah berdasarkan dokumen, rekod, dan maklumat yang telah dikemukakan oleh pihak-pihak berkaitan untuk tujuan rujukan dan pertimbangan Tribunal Tuntutan Pengguna Malaysia. Laporan ini disusun secara objektif bagi memberikan gambaran yang jelas dan teratur berhubung kedudukan semasa kecacatan sepanjang Tempoh Liabiliti Kecacatan (DLP). Kandungan laporan ini tidak bertujuan untuk membuat sebarang penilaian, kesimpulan, atau penentuan berhubung kesalahan, liabiliti, atau tanggungjawab undang-undang mana-mana pihak.",
                "",
                "6. Rumusan",
                "Laporan rujukan ini disediakan bagi merumuskan kedudukan semasa pematuhan Tempoh Liabiliti Kecacatan (DLP) berdasarkan sepenuhnya kepada rekod dan maklumat yang dikemukakan. Laporan ini menghimpunkan maklumat berkaitan status kecacatan, tempoh pelaksanaan, serta pematuhan terhadap garis masa yang ditetapkan untuk tujuan rujukan dan pertimbangan Tribunal. Laporan ini disediakan secara berkecuali dan tidak mengandungi sebarang penentuan kesalahan, liabiliti, atau keputusan undang-undang terhadap mana-mana pihak.",
                "",
                "PENAFIAN AI:",
                "Laporan rujukan ini dijana dengan bantuan sistem kecerdasan buatan (AI) bagi tujuan penyusunan dan ringkasan maklumat berdasarkan rekod yang dikemukakan. Laporan ini disediakan semata-mata untuk tujuan rujukan Tribunal dan tidak boleh dianggap sebagai nasihat undang-undang. Laporan ini tidak menggantikan penentuan atau keputusan Tribunal Tuntutan Pengguna Malaysia.",
            ])
    
    else:  # English language
        # Use translated report title and generated-at label; avoid duplicate AI header
        lines = [
            labels.get("report_title", "TRIBUNAL SUPPORT REPORT – DEFECT LIABILITY PERIOD (DLP)"),
            f"{labels.get('generated_at', 'Generated Date')}: {_fast_text(case_info.get('generated_datetime'))}",
            f"5. {labels['statement']}",
            labels["homeowner_request_text"].format(
                claim_amount=_fast_text(case_info.get("claim_amount")),
                item_service=_fast_text(case_info.get("item_service")),
                transaction_date=_format_display_date(case_info.get("transaction_date"), language),
            ),
            "",
        ]
        
        if role == "Homeowner":
            lines.append("Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)")
            lines.extend([
                "",
                "1. Purpose of Report",
                "This report is prepared to summarise and present defect records for the consideration of the Malaysia Consumer Claims Tribunal (TTPM) in relation to the claim submitted by the Claimant.",
                "",
                "2. Overview of Recorded Defects",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            critical = int(stats.get("critical_defects", 0) or 0)
            
            if total == 0:
                lines.append("Based on the records submitted, no defects have been reported during the Defect Liability Period (DLP). The total number of defects reported is 0, and there are no defects that are outstanding or critical.")
            else:
                lines.append(f"Based on the records submitted, the total number of defects reported is {total}. Of this number, {completed} have been completed, {pending} are still outstanding, and {critical} are categorized as critical.")
            
            lines.extend([
                "",
                "3. Detailed Defect Information",
            ])
            
            if defects:
                for index, defect in enumerate(defects, 1):
                    lines.append("")
                    lines.append(f"a. Defect ID {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Description: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Reported Date: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Scheduled Completion Date: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Actual Completion Date: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    
                    status_value = _status_label(_fast_text(defect.get("status"), ""), language)
                    if status_value == _fast_label(language, "completed"):
                        lines.append(f"   Days to Complete: {_fast_text(defect.get('days_to_complete'))}")
                    
                    lines.append(f"   Status: {status_value}")
                    lines.append(f"   Overdue Status: {_bool_label(defect.get('overdue'), language)}")
                    lines.append(f"   HDA Compliance Status: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
                    lines.append(f"   Priority: {_fast_text(defect.get('priority'), 'Normal')}")
                    remarks_text = _fast_text(defect.get("remarks"), "")
                    if remarks_text:
                        remarks = _translate(remarks_text, language, role, "defect_remark")
                    else:
                        remarks = _fast_label(language, "remarks_placeholder")
                    lines.append(f"   Remarks: {remarks}")
            else:
                lines.append("No defects have been reported for the purpose of Tribunal consideration.")
            
            overdue_count = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant_count = int(stats.get("hda_non_compliant_defects", 0) or 0)
            
            lines.extend([
                "",
                "4. Observations on Compliance and Deadlines",
            ])
            
            if total == 0:
                lines.append("No defects have exceeded the scheduled completion date or failed to comply with the 30-day HDA requirement, as no defects have been reported.")
            else:
                lines.append(f"Based on the records submitted, {overdue_count} defects have exceeded their scheduled completion dates, and {hda_non_compliant_count} defects do not comply with the 30-day requirement under the HDA.")
            
            lines.extend([
                "",
                "5. Formal Request from the Claimant",
                f"The Claimant has submitted a claim to the Malaysia Consumer Claims Tribunal for the amount of {_fast_text(case_info.get('claim_amount'))}, in relation to {_fast_text(case_info.get('item_service'))} carried out on {_format_display_date(case_info.get('transaction_date'), language)}.",
                "",
                "6. Conclusion",
                "This support report is prepared solely to summarise and present information relating to defects reported during the Defect Liability Period (DLP), based on the records submitted by the Claimant, for the purpose of reference and consideration by the Malaysia Consumer Claims Tribunal, without making any determination of fault, liability, or legal decision.",
                "",
                _fast_label(language, "ai_disclaimer_title"),
                _fast_label(language, "ai_disclaimer_text"),
            ])
        
        elif role == "Developer":
            lines.append("Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)")
            claimant_unit = report_data.get("claimant_unit", "")
            
            lines.extend([
                "",
                "1. Purpose of Report",
                "This report is prepared to present the current status of rectification works undertaken during the Defect Liability Period (DLP) based on internal developer records.",
                "",
                "2. Overview of Rectification Status",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            overdue = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant = int(stats.get("hda_non_compliant_defects", 0) or 0)
            
            lines.append(f"The total number of recorded defects is {total}. Of this number, {completed} have been completed and {pending} are still outstanding. There are {overdue} defects that have exceeded the scheduled completion date and {hda_non_compliant} defects that do not comply with the 30-day requirement under the HDA.")
            
            lines.extend([
                "",
                "3. Completed Rectification Works",
            ])
            
            completed_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) in {"Completed", "Telah Diselesaikan"}]
            if completed_defects:
                for index, defect in enumerate(completed_defects, 1):
                    lines.append("")
                    lines.append(f"a. Defect ID {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Description: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Reported Date: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Scheduled Completion Date: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Actual Completion Date: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    lines.append(f"   Days to Complete: {_fast_text(defect.get('days_to_complete'))}")
                    lines.append(f"   HDA Compliance Status: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
            else:
                lines.append("No completed defects are recorded.")
            
            lines.extend([
                "",
                "4. Outstanding or Delayed Rectification Works",
            ])
            
            pending_defects = [d for d in defects if _status_label(_fast_text(d.get("status"), ""), language) not in {"Completed", "Telah Diselesaikan"}]
            if pending_defects:
                for index, defect in enumerate(pending_defects, 1):
                    lines.append("")
                    lines.append(f"a. Defect ID {_fast_text(defect.get('defect_id'))}:")
                    description = _translate(_fast_text(defect.get('description')), language, role, "defect_description")
                    lines.append(f"   Description: {description}")
                    lines.append(f"   Unit: {_fast_text(defect.get('unit'))}")
                    lines.append(f"   Reported Date: {_format_display_date(defect.get('reported_date'), language)}")
                    lines.append(f"   Scheduled Completion Date: {_format_display_date(defect.get('deadline'), language)}")
                    lines.append(f"   Actual Completion Date: {_format_display_date(defect.get('actual_completion_date'), language)}")
                    status_value = _status_label(_fast_text(defect.get("status"), ""), language)
                    lines.append(f"   Current Status: {status_value}")
                    lines.append(f"   Overdue Status: {_bool_label(defect.get('overdue'), language)}")
                    lines.append(f"   HDA Compliance Status: {_hda_compliance_label(defect.get('hda_compliance_30_days'), language, defect.get('status'))}")
            else:
                lines.append("No outstanding or delayed defects are recorded.")
            
            lines.extend([
                "",
                "5. Observations on Timeframe Compliance",
                f"Based on the records submitted, {overdue} defects have exceeded their scheduled completion dates, and {hda_non_compliant} defects do not comply with the thirty (30) day requirement under the Housing Development Act (HDA).",
                "",
                "6. Developer's Commitment Statement",
                "The developer is committed to continue carrying out rectification works for defects that are still recorded as unresolved based on the information available in the records.",
                "",
                "7. Conclusion",
                "This compliance report is prepared to summarise the status of rectification works during the Defect Liability Period based on internal records available, for the purpose of reference and consideration by the Tribunal, without any admission of fault, liability, or legal responsibility.",
                "",
                _fast_label(language, "ai_disclaimer_title"),
                _fast_label(language, "developer_ai_disclaimer_text"),
            ])
        
        else:  # Legal role
            lines.append("Overview Report on Defect Liability Period (DLP) Compliance")
            
            lines.extend([
                "",
                "1. Case Background",
                f"Claim reference number: {_fast_text(case_info.get('claim_id'))}. Claim amount: {_fast_text(case_info.get('claim_amount'))}. Total number of recorded defects: {_fast_text(stats.get('total_defects'))}.",
                "",
                "2. Statistical Position of Defect Records",
            ])
            
            total = int(stats.get("total_defects", 0) or 0)
            completed = int(stats.get("completed_defects", 0) or 0)
            pending = int(stats.get("pending_defects", 0) or 0)
            overdue = int(stats.get("overdue_defects", 0) or 0)
            hda_non_compliant = int(stats.get("hda_non_compliant_defects", 0) or 0)
            closed = int(stats.get("closed_defects", 0) or 0)
            
            lines.extend([
                f"Total recorded defects: {total}",
                f"Completed: {completed}",
                f"Closed Cases: {closed}",
                f"Still unresolved: {pending}",
                f"Recorded as overdue: {overdue}",
                f"Non-compliant with 30-day HDA requirement: {hda_non_compliant}",
            ])
            
            lines.extend([
                "",
                "3. Recorded Status and Timeframe Observations",
                f"Based on the records submitted, {total} defects have been recorded. Of this number, {completed} have been completed and {pending} are still in progress. There are {overdue} defects that have exceeded their scheduled completion dates and {hda_non_compliant} defects that do not comply with the 30-day requirement under the HDA.",
                "",
                "4. Observations on Outstanding or Delayed Matters",
                f"Based on the records submitted, {overdue} defects have exceeded their scheduled completion dates and remain unresolved. These defects are recorded as outstanding, delayed, or still in progress beyond the prescribed timeframe.",
                "",
                "5. Notes for Tribunal Consideration",
                "The information presented in this report is based strictly on the documents, records, and information submitted by the relevant parties for the purpose of reference and consideration by the Malaysia Consumer Claims Tribunal. This report has been prepared in an objective manner to present a clear and structured overview of the current status of defects during the Defect Liability Period (DLP). The contents of this report are not intended to make any assessment, conclusion, or determination regarding fault, liability, or legal responsibility of any party.",
                "",
                "6. Summary",
                "This reference report is prepared to summarise the current position of compliance with the Defect Liability Period (DLP) based strictly on the records and information submitted. This report consolidates information relating to defect status, completion timelines, and compliance with the prescribed timeframe for the purpose of Tribunal reference and consideration. The report is presented in a neutral manner and does not contain any determination of fault, liability, or legal conclusion against any party.",
                "",
                _fast_label(language, "ai_disclaimer_title"),
                _fast_label(language, "legal_ai_disclaimer_text"),
            ])

    out = "\n".join(lines).strip()
    out = _ensure_disclaimer_localized(out, language)
    return out


def generate_ai_report(role, report_data, language="ms"):
    if os.getenv("ENABLE_AI_REPORT_GENERATION", "0") != "1":
        return generate_fast_report(role, report_data, language)

    client = get_ai_client()
    timeout_seconds = float(os.getenv("AI_TIMEOUT_SECONDS", "180"))
    lang_config = get_language_config(language)
    report_data = _prepare_role_specific_defect_groups(report_data, role)
    prompt = build_prompt(role, report_data, language)
    generated_datetime_label = lang_config.get("generated_label", "Generated Date")
    generated_datetime_value = report_data.get("case_info", {}).get("generated_datetime") or _format_generated_datetime(language)

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": lang_config["system_instruction"]},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=2048,
            timeout=timeout_seconds,
        )
        ai_text = response.choices[0].message.content or ""
        if not ai_text.strip():
            ai_text = "This report is generated based on the records submitted."
    except Exception as e:
        error_msg = str(e)
        if "quota" in error_msg.lower() or "429" in error_msg or "rate" in error_msg.lower():
            raise Exception("Groq API rate limit reached. Please try again in a moment.")
        if "401" in error_msg or "invalid" in error_msg.lower() or "api_key" in error_msg.lower():
            raise Exception("Invalid Groq API key. Please check your API key configuration.")
        raise Exception(f"Groq AI API error: {error_msg}")

    # Ensure full report is consistently in the requested language
    try:
        try:
            from .ai_translate_cached import translate_report_cached
        except ImportError:
            from ai_translate_cached import translate_report_cached

        ai_text = translate_report_cached(ai_text, language=language, role=role)
    except Exception:
        # If translation post-processing fails, fall back to original AI text
        pass

    # Add AI report header
    # Remove any existing generated datetime / title lines from AI output to avoid duplicates
    try:
        ai_text = refresh_generated_datetime_line(ai_text, language)
        # Remove leading report title if AI already included it
        title_pattern = re.escape(lang_config.get("report_title", "").strip())
        ai_text = re.sub(rf"^\s*{title_pattern}\s*\n", "", ai_text)
        # Remove AI's own short title if present
        ai_text = re.sub(rf"^\s*LAPORAN RINGKASAN TUNTUTAN DIJANA AI\s*\n", "", ai_text, flags=re.IGNORECASE)
        ai_text = re.sub(rf"^\s*AI-GENERATED CLAIM SUMMARY REPORT\s*\n", "", ai_text, flags=re.IGNORECASE)
        ai_text = ai_text.strip()
    except Exception:
        pass

    # Prepend canonical report header for English only; avoid duplicating titles for Malay
    if (language or "").strip().lower() == "en":
        out = (
            f"{lang_config.get('ai_title', '')}\n\n"
            f"{lang_config.get('report_title', '')}\n"
            f"{generated_datetime_label}: {generated_datetime_value}\n\n"
            f"{ai_text}"
        ).strip()
    else:
        # For non-English (Malay) output, only include the generated datetime and the AI text
        out = (
            f"{generated_datetime_label}: {generated_datetime_value}\n\n"
            f"{ai_text}"
        ).strip()

    # Ensure AI disclaimer heading uses the requested language
    out = _ensure_disclaimer_localized(out, language)
    return out


def add_legal_metadata(
    report_content: str,
    report_id: str,
    user_id: int,
    role: str,
    defects: list,
    status_store: dict,
    completion_store: dict,
    language: str = "ms",
) -> dict:
    legal_manager = get_legal_manager()
    signature_timestamp = legal_manager._now_app_timezone()
    report_id = legal_manager.build_public_report_id(report_id, signature_timestamp)
    signature = legal_manager.generate_digital_signature(
        report_id=report_id,
        report_content=report_content,
        user_id=user_id,
        role=role,
        timestamp=signature_timestamp,
    )
    timeline = legal_manager.create_event_timeline(
        report_id=report_id,
        defects=defects,
        status_store=status_store,
        completion_store=completion_store,
        language=language,
    )
    certificate = legal_manager.create_compliance_certificate(
        report_id=report_id,
        defects=defects,
        signature_data=signature,
        language=language,
        role=role,
    )
    legal_manager.log_event(
        action="report_generated",
        report_id=report_id,
        user_id=user_id,
        role=role,
        details={"language": language, "defect_count": len(defects)},
    )
    return {
        "report_id": report_id,
        "report_content": report_content,
        "signature": signature,
        "timeline": timeline,
        "certificate": certificate,
        "legal_footer": legal_manager.get_legal_footer(language),
    }


def format_legal_report(
    report_content: str,
    legal_metadata: dict,
    language: str = "ms",
) -> str:
    footer = legal_metadata.get("legal_footer", "")
    signature = legal_metadata.get("signature", {})
    certificate = legal_metadata.get("certificate", {})

    labels = {
        "ms": {
            "signature_section": "BAHAGIAN TANDATANGAN DIGITAL",
            "certificate_no": "No. Sijil",
            "signature_id": "ID Tandatangan",
            "timestamp": "Tarikh & Masa",
            "hash": "Cincang Integriti",
            "certificate_section": "SIJIL PEMATUHAN",
            "compliance_status": "Status Pematuhan",
            "event_timeline": "GARIS MASA PERISTIWA",
        },
        "en": {
            "signature_section": "DIGITAL SIGNATURE SECTION",
            "certificate_no": "Certificate No.",
            "signature_id": "Signature ID",
            "timestamp": "Timestamp",
            "hash": "Integrity Hash",
            "certificate_section": "COMPLIANCE CERTIFICATE",
            "compliance_status": "Compliance Status",
            "event_timeline": "EVENT TIMELINE",
        },
    }

    lang_labels = labels.get(language, labels["ms"])
    status_values = {
        "ms": {
            "COMPLIANT": "Mematuhi",
            "PENDING_REVIEW": "Tidak Mematuhi",
            "PENDING": "Tidak Mematuhi",
            "NON_COMPLIANT": "Tidak Mematuhi",
        },
        "en": {
            "COMPLIANT": "Compliant",
            "PENDING_REVIEW": "Non-Compliant",
            "PENDING": "Non-Compliant",
            "NON_COMPLIANT": "Non-Compliant",
        },
    }.get(language, {})
    raw_compliance_status = certificate.get("compliance_status", "PENDING")
    compliance_status = status_values.get(raw_compliance_status, raw_compliance_status)

    formatted = f"""{report_content}

---

{lang_labels['signature_section']}
{lang_labels['certificate_no']}: {certificate.get('certificate_no', certificate.get('certificate_id', 'N/A'))}
{lang_labels['signature_id']}: {signature.get('signature_id', 'N/A')}
{lang_labels['timestamp']}: {signature.get('timestamp', 'N/A')}
{lang_labels['hash']}: {signature.get('content_hash', 'N/A')[:32]}...

{lang_labels['certificate_section']}
{lang_labels['compliance_status']}: {compliance_status}

{lang_labels['event_timeline']}
{legal_metadata.get('timeline', {}).get('summary', 'No events')}

---

{footer}
"""
    return formatted.strip()
