# config_mappings.py

# ======================================
# STATUS NORMALISATION (ALWAYS → ENGLISH)
# ======================================
STATUS_NORMALISE = {
    "Belum Diselesaikan": "Pending",
    "Dalam Tindakan": "In Progress",
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
        "In Progress": "Dalam Tindakan",
        "Completed": "Telah Diselesaikan",
        "Closed": "Ditutup",
        "Archived": "Ditutup",
        "Delayed": "Tertangguh",
    },
    "en": {
        "Belum Diselesaikan": "Pending",
        "Dalam Tindakan": "In Progress",
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
