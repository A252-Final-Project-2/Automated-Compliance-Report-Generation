# config_pdf_labels.py

PDF_LABELS = {
    "ms": {
        # General
        "page": "Halaman",
        "ai_title": "LAPORAN RINGKASAN TUNTUTAN DIJANA AI",
        "report_title": "LAPORAN SOKONGAN TRIBUNAL – TEMPOH LIABILITI KECACATAN (DLP)",
        "homeowner_report_title": "LAPORAN SOKONGAN TRIBUNAL - TEMPOH LIABILITI KECACATAN (DLP)",
        "developer_report_title": "LAPORAN PEMATUHAN RESPONDEN - TEMPOH LIABILITI KECACATAN (DLP)",
        "legal_report_title": "LAPORAN RUJUKAN TRIBUNAL - TEMPOH LIABILITI KECACATAN (DLP)",
        "generated_at": "Tarikh Jana",
        "homeowner_report_subtitle": "Laporan Sokongan Bagi Tuntutan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
        "developer_report_subtitle": "Laporan Pematuhan Bagi Rujukan Tribunal Tuntutan Pengguna Malaysia (TTPM)",
        "legal_report_subtitle": "Laporan Gambaran Keseluruhan Pematuhan Tempoh Liabiliti Kecacatan (DLP)",

        # Filenames
        "legal_filename": "Laporan_Rujukan_Tribunal_DLP.pdf",
        "developer_filename": "Laporan_Pematuhan_DLP_Responden.pdf",
        "homeowner_filename": "Borang1_Pernyataan_Tuntutan_DLP_Penuntut.pdf",


        # HARD STATUS TRANSLATION
        "status_map": {
            "Pending": "Belum Diselesaikan",
            "In Progress": "Dalam Proses",
            "Completed": "Telah Diselesaikan",
            "Closed": "Ditutup",
            "Archived": "Ditutup",
            "Delayed": "Lewat"
        },

        # Defect List labels
        "defect_list": "Senarai Kecacatan",
        "defect_id": "Kecacatan ID",
        "description": "Keterangan",
        "unit": "Unit",
        "reported_date": "Tarikh Dilaporkan",
        "deadline": "Tarikh Siap Dijadualkan",
        "actual_completion_date": "Tarikh Siap Sebenar",
        "status": "Status",
        "overdue": "Status Tertunggak",
        "hda_compliant": "Status Pematuhan HDA",
        "priority": "Keutamaan",
        "remarks": "Ulasan",
        "evidence": "Bukti Kecacatan",

        # Legal Metadata
        "legal_metadata": {
            "title": "SIJIL PEMATUHAN PERUNDANGAN",
            "titles": {
                "Homeowner": {
                    "ms": "Sijil Ringkasan Pematuhan Rekod Kecacatan",
                    "en": "Certificate of Defect Record Compliance Summary",
                },
                "Developer": {
                    "ms": "Sijil Ringkasan Pematuhan Pelaksanaan Pembaikan",
                    "en": "Certificate of Defect Rectification Compliance Summary",
                },
                "Legal": {
                    "ms": "Sijil Ringkasan Pematuhan Perundangan",
                    "en": "Certificate of Legal Compliance Summary",
                },
            },
            "report_info": "Maklumat Laporan",
            "compliance": "Status Pematuhan",
            "defect_summary": "Ringkasan Kecacatan",
            "integrity": "Integriti Data",
            "timeline": "Ringkasan Garis Masa",
            "report_id": "ID Laporan",
            "signature_id": "ID Tandatangan",
            "timestamp": "Tarikh & Masa",
            "status": "Status",
            "status_values": {
                "COMPLIANT": "Mematuhi",
                "PENDING_REVIEW": "Tidak Mematuhi",
                "PENDING": "Tidak Mematuhi",
                "NON_COMPLIANT": "Tidak Mematuhi"
            },
            "total": "Jumlah Kecacatan",
            "completed": "Telah Selesai",
            "rate": "Kadar Penyelesaian",
            "no_timeline": "Tiada rekod"
        }
    },

    "en": {
        # General
        "page": "Page",
        "ai_title": "AI-GENERATED CLAIM SUMMARY REPORT",
        "report_title": "TRIBUNAL SUPPORT REPORT - DEFECT LIABILITY PERIOD (DLP)",
        "homeowner_report_title": "TRIBUNAL SUPPORT REPORT - DEFECT LIABILITY PERIOD (DLP)",
        "developer_report_title": "RESPONDENT COMPLIANCE REPORT - DEFECT LIABILITY PERIOD (DLP)",
        "legal_report_title": "TRIBUNAL REFERENCE REPORT - DEFECT LIABILITY PERIOD (DLP)",
        "generated_at": "Generated Date",
        "homeowner_report_subtitle": "Support Report for Claim before the Malaysia Consumer Claims Tribunal (TTPM)",
        "developer_report_subtitle": "Compliance Report for Reference before the Malaysia Consumer Claims Tribunal (TTPM)",
        "legal_report_subtitle": "Overview Report on Defect Liability Period (DLP) Compliance",

        # Filenames
        "legal_filename": "Tribunal_Reference_Report_DLP.pdf",
        "developer_filename": "Respondent_DLP_Compliance_Report.pdf",
        "homeowner_filename": "Claimant_Form1_Statement_of_Claim_DLP.pdf",

        # ENGLISH = identity
        "status_map": {
            "Pending": "Pending",
            "In Progress": "In Progress",
            "Completed": "Completed",
            "Closed": "Closed",
            "Archived": "Closed",
            "Delayed": "Delayed"
        },

        # Defect List labels
        "defect_list": "Defect List",
        "defect_id": "Defect ID",
        "description": "Description",
        "unit": "Unit",
        "reported_date": "Reported Date",
        "deadline": "Scheduled Completion Date",
        "actual_completion_date": "Actual Completion Date",
        "status": "Status",
        "overdue": "Overdue Status",
        "hda_compliant": "HDA Compliance Status",
        "priority": "Priority",
        "remarks": "Remarks",
        "evidence": "Defect Evidence",

         # Legal Metadata
        "legal_metadata": {
            "title": "LEGAL COMPLIANCE CERTIFICATE",
            "titles": {
                "Homeowner": {
                    "ms": "Certificate of Defect Record Compliance Summary",
                    "en": "Certificate of Defect Record Compliance Summary",
                },
                "Developer": {
                    "ms": "Certificate of Remedial Work Compliance",
                    "en": "Certificate of Remedial Work Compliance",
                },
                "Legal": {
                    "ms": "Legal Compliance Certificate (For Tribunal Reference)",
                    "en": "Legal Compliance Certificate (For Tribunal Reference)",
                },
            },
            "report_info": "Report Information",
            "compliance": "Compliance Status",
            "defect_summary": "Defect Summary",
            "integrity": "Data Integrity",
            "timeline": "Timeline Summary",
            "report_id": "Report ID",
            "signature_id": "Signature ID",
            "timestamp": "Timestamp",
            "status": "Status",
            "status_values": {
                "COMPLIANT": "Compliant",
                "PENDING_REVIEW": "Non-Compliant",
                "PENDING": "Non-Compliant",
                "NON_COMPLIANT": "Non-Compliant"
            },
            "total": "Total Defects",
            "completed": "Completed",
            "rate": "Completion Rate",
            "no_timeline": "No events recorded"
        }
    }
}
