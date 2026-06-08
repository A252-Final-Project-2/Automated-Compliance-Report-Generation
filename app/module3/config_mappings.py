# config_mappings.py

# ======================================
# STATUS NORMALISATION (ALWAYS → ENGLISH)
# ======================================
STATUS_NORMALISE = {
    "Belum Diselesaikan": "Pending",
    "Dalam Semakan": "Pending",
    "Under Review": "Pending",
    "Dalam Tindakan": "In Progress",
    "Dalam Proses Pematuhan": "In Progress",
    "Compliance In Progress": "In Progress",
    "Telah Diselesaikan": "Completed",
    "Ditutup": "Closed",
    "Diarkib": "Archived",
    "Tertangguh": "Delayed",
}

# ======================================
# STATUS TRANSLATION (FOR DISPLAY)
# ======================================
STATUS_TRANSLATION = {
    "ms": {
        "Pending": "Belum Diselesaikan",
        "Under Review": "Belum Diselesaikan",
        "In Progress": "Dalam Tindakan",
        "Compliance In Progress": "Dalam Tindakan",
        "Completed": "Telah Diselesaikan",
        "Closed": "Ditutup",
        "Archived": "Ditutup",
        "Delayed": "Tertangguh",
    },
    "en": {
        "Pending": "Pending",
        "In Progress": "In Progress",
        "Belum Diselesaikan": "Pending",
        "Dalam Semakan": "Pending",
        "Dalam Tindakan": "In Progress",
        "Dalam Proses Pematuhan": "In Progress",
        "Telah Diselesaikan": "Completed",
        "Ditutup": "Closed",
        "Diarkib": "Closed",
        "Archived": "Closed",
        "Tertangguh": "Delayed",
    }
}

# ======================================
# PRIORITY TRANSLATION
# ======================================
PRIORITY_TRANSLATION = {
    "ms": {
        "High": "Tinggi",
        "Medium": "Sederhana",
        "Low": "Rendah",
    },
    "en": {
        "Tinggi": "High",
        "Sederhana": "Medium",
        "Rendah": "Low",
    }
}
