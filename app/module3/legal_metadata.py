# legal_metadata.py
"""
Legal Metadata & Digital Signatures Module for DLP-CRAM
Generates digital signatures, event timelines, and compliance markers
for tribunal-grade documentation.
"""

import os
import json
import hashlib
import hmac
import uuid
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Dict, List, Optional, Any

try:
    from .database.db import get_connection
except ImportError:  # pragma: no cover
    from database.db import get_connection


class LegalMetadataManager:
    """Manages digital signatures, event timelines, and legal compliance metadata."""

    def __init__(self):
        self.app_timezone = os.getenv("APP_TIMEZONE", "Asia/Kuala_Lumpur")
        self.signature_key = os.getenv("LEGAL_SIGNATURE_KEY", "dlp-cram-signature-key-default")
        self.event_log_path = "audit_data/event_timeline.json"

    def _now_app_timezone(self) -> datetime:
        """Get current time in app timezone with precision."""
        try:
            return datetime.now(ZoneInfo(self.app_timezone))
        except Exception:
            if self.app_timezone == "Asia/Kuala_Lumpur":
                return datetime.now(timezone.utc) + timedelta(hours=8)
            return datetime.now(timezone.utc)

    def _is_internal_identifier(self, value: str) -> bool:
        text = str(value or "").strip()
        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", text):
            return True
        return bool(re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F]{64}", text))

    def build_public_report_id(self, report_id: str, timestamp: Optional[datetime] = None) -> str:
        report_ref = str(report_id or "").strip()
        if timestamp is None:
            timestamp = self._now_app_timezone()

        if report_ref and report_ref.upper() not in {"N/A", "-"} and not self._is_internal_identifier(report_ref):
            return re.sub(r"[^A-Za-z0-9/-]+", "-", report_ref).strip("-")

        return f"RPT/{timestamp.strftime('%Y%m%d-%H%M%S')}"

    def _build_public_signature_id(self, report_id: str, timestamp: datetime) -> str:
        report_ref = self.build_public_report_id(report_id, timestamp)
        timestamp_ref = timestamp.strftime("%Y%m%d-%H%M%S")

        return f"SIG/{report_ref}/{timestamp_ref}"

    def build_public_certificate_no(self, report_id: str, timestamp: Optional[datetime] = None) -> str:
        report_ref = self.build_public_report_id(report_id, timestamp)
        if timestamp is None:
            timestamp = self._now_app_timezone()

        match = re.fullmatch(r"TTPM/[A-Za-z0-9]+/(\d{4})/(\d+)", report_ref)
        if match:
            year, running_no = match.groups()
            return f"CERT-DLP-{year}-{int(running_no):06d}"

        match = re.search(r"(\d{4})(\d{2})(\d{2})-(\d{6})", report_ref)
        if match:
            year = match.group(1)
            compact_ref = f"{match.group(2)}{match.group(3)}{match.group(4)}"
            return f"CERT-DLP-{year}-{compact_ref}"

        return f"CERT-DLP-{timestamp.strftime('%Y')}-{timestamp.strftime('%m%d%H%M%S')}"

    def generate_digital_signature(
        self,
        report_id: str,
        report_content: str,
        user_id: int,
        role: str,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Generate a cryptographic digital signature for legal compliance.
        
        Args:
            report_id: Unique report identifier
            report_content: The report text to sign
            user_id: User generating the report
            role: User role (Homeowner, Developer, Legal, Admin)
            timestamp: Optional timestamp (uses current time if None)
        
        Returns:
            Dict with signature, timestamp, hash, and metadata
        """
        if timestamp is None:
            timestamp = self._now_app_timezone()
        
        report_id = self.build_public_report_id(report_id, timestamp)
        timestamp_iso = timestamp.isoformat()
        
        # Create signing data
        signing_data = f"{report_id}|{user_id}|{role}|{timestamp_iso}|{report_content[:100]}"
        
        # Generate HMAC-SHA256 signature
        signature = hmac.new(
            self.signature_key.encode(),
            signing_data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Generate content hash (for integrity verification)
        content_hash = hashlib.sha256(report_content.encode()).hexdigest()
        
        return {
            "signature_id": self._build_public_signature_id(report_id, timestamp),
            "signature": signature,
            "content_hash": content_hash,
            "timestamp": timestamp_iso,
            "timestamp_unix": int(timestamp.timestamp()),
            "user_id": user_id,
            "role": role,
            "report_id": report_id,
            "algorithm": "HMAC-SHA256",
            "compliance_standard": "DLP-CRAM Legal Metadata v1.0"
        }

    def verify_signature(
        self,
        signature_data: Dict[str, Any],
        report_content: str
    ) -> bool:
        """
        Verify a digital signature for report integrity.
        
        Args:
            signature_data: The signature metadata to verify
            report_content: The report content to verify against
        
        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Recreate the signed data
            signing_data = (
                f"{signature_data['report_id']}|{signature_data['user_id']}|"
                f"{signature_data['role']}|{signature_data['timestamp']}|{report_content[:100]}"
            )
            
            # Verify HMAC-SHA256
            expected_signature = hmac.new(
                self.signature_key.encode(),
                signing_data.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Verify content hash
            content_hash = hashlib.sha256(report_content.encode()).hexdigest()
            
            return (
                signature_data["signature"] == expected_signature and
                signature_data["content_hash"] == content_hash
            )
        except Exception:
            return False

    def create_event_timeline(
        self,
        report_id: str,
        defects: List[Dict],
        status_store: Dict,
        completion_store: Dict,
        language: str = "ms"
    ) -> Dict[str, Any]:
        """
        Create a comprehensive event timeline for tribunal submissions.
        
        Args:
            report_id: Report identifier
            defects: List of defect records
            status_store: Defect status history
            completion_store: Completion date history
            language: "ms" or "en"
        
        Returns:
            Structured event timeline for legal proceedings
        """
        events = []
        
        # Timeline labels
        labels = {
            "ms": {
                "reported": "Dilaporkan",
                "acknowledged": "Diakui",
                "in_progress": "Dalam Tindakan",
                "completed": "Selesai",
                "verified": "Disahkan",
                "closed": "Ditutup",
                "lad_deadline": "Tarikh Akhir LAD",
                "no_events": "Tiada rekod peristiwa.",
                "timeline_summary": "Ringkasan Garis Masa",
                "completed_count": "selesai",
                "pending_count": "belum selesai",
                "initial_report": "Laporan awal",
                "last_update": "Kemas kini terakhir"
            },
            "en": {
                "reported": "Reported",
                "acknowledged": "Acknowledged",
                "in_progress": "In Progress",
                "completed": "Completed",
                "verified": "Verified",
                "closed": "Closed",
                "lad_deadline": "LAD Deadline",
                "no_events": "No events recorded.",
                "timeline_summary": "Timeline Summary",
                "completed_count": "completed",
                "pending_count": "pending",
                "initial_report": "Initial report",
                "last_update": "Last update"
            }
        }
        
        lang_labels = labels.get(language, labels["ms"])
        
        for defect in defects:
            defect_id = str(defect.get("id"))
            
            # Report event
            events.append({
                "timestamp": defect.get("reported_date"),
                "event_type": "reported",
                "label": lang_labels["reported"],
                "defect_id": defect_id,
                "description": f"Defect {defect_id} reported: {defect.get('desc', 'N/A')}",
                "status": "Pending"
            })
            
            # Completion event
            if defect.get("completed_date") and defect.get("status") in ["Completed", "Closed"]:
                events.append({
                    "timestamp": defect.get("completed_date"),
                    "event_type": "completed",
                    "label": lang_labels["completed"],
                    "defect_id": defect_id,
                    "description": f"Defect {defect_id} repair completed",
                    "status": "Completed"
                })
            
            # LAD deadline event
            if defect.get("deadline"):
                events.append({
                    "timestamp": defect.get("deadline"),
                    "event_type": "lad_deadline",
                    "label": lang_labels["lad_deadline"],
                    "defect_id": defect_id,
                    "description": f"LAD deadline for defect {defect_id}",
                    "status": "Deadline"
                })
        
        # Sort by timestamp
        events.sort(key=lambda x: x.get("timestamp", ""), reverse=False)
        
        return {
            "report_id": report_id,
            "timeline_generated": self._now_app_timezone().isoformat(),
            "event_count": len(events),
            "events": events,
            "summary": self._generate_timeline_summary(events, lang_labels)
        }

    def _generate_timeline_summary(self, events: List[Dict], labels: Dict) -> str:
        """Generate a text summary of the event timeline."""
        if not events:
            return labels.get("no_events", "No events recorded.")
        
        first_event = events[0] if events else None
        last_event = events[-1] if events else None
        
        pending_count = len([e for e in events if e.get("status") == "Pending"])
        completed_count = len([e for e in events if e.get("status") == "Completed"])
        
        summary = (
            f"{labels.get('timeline_summary', 'Timeline Summary')}: "
            f"{completed_count} {labels.get('completed_count', 'completed')}, "
            f"{pending_count} {labels.get('pending_count', 'pending')}. "
            f"{labels.get('initial_report', 'Initial report')}: {first_event.get('timestamp', 'N/A')}. "
            f"{labels.get('last_update', 'Last update')}: {last_event.get('timestamp', 'N/A')}."
        )
        return summary

    def log_event(
        self,
        action: str,
        report_id: str,
        user_id: int,
        role: str,
        defect_id: Optional[str] = None,
        details: Optional[Dict] = None
    ) -> None:
        """
        Log an event to the audit trail for compliance.
        
        Args:
            action: Action type (generate, export, sign, verify)
            report_id: Report identifier
            user_id: User performing action
            role: User role
            defect_id: Optional defect ID
            details: Optional additional details
        """
        try:
            event_timestamp = self._now_app_timezone()
            report_id = self.build_public_report_id(report_id, event_timestamp)
            details = details.copy() if isinstance(details, dict) else {}
            signature_id = str(details.get("signature_id") or "").strip()
            if signature_id and self._is_internal_identifier(signature_id):
                details["signature_id"] = self._build_public_signature_id(report_id, event_timestamp)

            # Ensure directory exists
            os.makedirs(os.path.dirname(self.event_log_path), exist_ok=True)
            
            # Load existing events
            events = []
            if os.path.exists(self.event_log_path):
                try:
                    with open(self.event_log_path, "r") as f:
                        events = json.load(f)
                except Exception:
                    events = []
            
            # Append new event
            event = {
                "event_id": str(uuid.uuid4()),
                "timestamp": event_timestamp.isoformat(),
                "action": action,
                "report_id": report_id,
                "user_id": user_id,
                "role": role,
                "defect_id": defect_id,
                "details": details,
            }
            
            events.append(event)
            
            # Save updated events
            with open(self.event_log_path, "w") as f:
                json.dump(events, f, indent=2, default=str)
        
        except Exception as e:
            # Log to stderr but don't crash
            print(f"Warning: Could not log event: {e}", flush=True)

    def create_compliance_certificate(
        self,
        report_id: str,
        defects: List[Dict],
        signature_data: Dict[str, Any],
        language: str = "ms",
        role: str = "Legal"
    ) -> Dict[str, Any]:
        """
        Create a legal compliance certificate for the report.
        
        Args:
            report_id: Report identifier
            defects: List of defect records
            signature_data: Digital signature metadata
            language: Report language
        
        Returns:
            Compliance certificate with legal metadata
        """
        now = self._now_app_timezone()
        
        titles = {
            "Homeowner": {
                "ms": "Sijil Ringkasan Pematuhan Rekod Kecacatan",
                "en": "Certificate of Defect Record Compliance Summary",
            },
            "Developer": {
                "ms": "Sijil Pematuhan Pelaksanaan Pembetulan",
                "en": "Certificate of Remedial Work Compliance",
            },
            "Legal": {
                "ms": "Sijil Pematuhan Perundangan (Untuk Rujukan Tribunal)",
                "en": "Legal Compliance Certificate (For Tribunal Reference)",
            },
        }

        labels = {
            "ms": {
                "title": titles.get(role, titles["Legal"]).get("ms", titles["Legal"]["ms"]),
                "report_id": "ID Laporan",
                "issued_date": "Tarikh Pengeluaran",
                "signature": "Tandatangan Digital",
                "hash": "Cincang Integriti",
                "compliance": "Status Pematuhan",
                "valid": "Sah untuk Tribunal",
                "standard": "Piawai Pematuhan"
            },
            "en": {
                "title": titles.get(role, titles["Legal"]).get("en", titles["Legal"]["en"]),
                "report_id": "Report ID",
                "issued_date": "Issued Date",
                "signature": "Digital Signature",
                "hash": "Integrity Hash",
                "compliance": "Compliance Status",
                "valid": "Valid for Tribunal",
                "standard": "Compliance Standard"
            }
        }

        lang_labels = labels.get(language, labels["ms"])
        
        def _status_value(defect):
            return str(defect.get("status", "")).strip().lower()

        def _is_completed(defect):
            return defect.get("closed") or _status_value(defect) in {
                "completed",
                "closed",
                "archived",
                "telah diselesaikan",
                "telah selesai",
                "selesai",
                "ditutup",
                "diarkib",
            }

        def _is_pending(defect):
            return _status_value(defect) in {"pending", "belum diselesaikan", "belum selesai"}

        report_id = self.build_public_report_id(report_id, now)

        # Calculate defect statistics
        total_defects = len(defects)
        completed = len([d for d in defects if _is_completed(d)])
        pending = len([d for d in defects if _is_pending(d)])
        
        return {
            "certificate_id": self.build_public_certificate_no(report_id, now),
            "certificate_no": self.build_public_certificate_no(report_id, now),
            "certificate_title": lang_labels["title"],
            "report_id": report_id,
            "issued_date": now.isoformat(),
            "signature_id": signature_data.get("signature_id"),
            "digital_signature": signature_data.get("signature")[:32] + "...",  # Truncated for display
            "integrity_hash": signature_data.get("content_hash"),
            "compliance_status": "COMPLIANT" if completed >= total_defects * 0.80 else "PENDING_REVIEW",
            "valid_for_tribunal": True,
            "compliance_standard": "HDA 1966 / CIPAA 2012",
            "statistics": {
                "total_defects": total_defects,
                "completed": completed,
                "pending": pending,
                "completion_rate": f"{(completed / total_defects * 100):.1f}%" if total_defects > 0 else "0%"
            },
            "labels": lang_labels
        }

    def get_legal_footer(self, language: str = "ms") -> str:
        """
        Get legal footer text for report PDFs.
        
        Args:
            language: "ms" for Bahasa Malaysia, "en" for English
        
        Returns:
            Legal footer text with digital signature info
        """
        footers = {
            "ms": (
                "Laporan ini disertakan dengan tandatangan digital untuk tujuan "
                "pengesahan integriti dan pematuhan di bawah Undang-undang Pembangunan Perumahan "
                "(Kawalan dan Lesen) 1966 (UUM 1966) dan Akta Pembayaran dan Penyelarasan Industri "
                "Pembinaan 2012 (CIPAA 2012). Tandatangan digital ini tidak menggantikan tandatangan "
                "tangan manual dan hanya untuk rujukan Tribunal."
            ),
            "en": (
                "This report is accompanied by a digital signature for the purpose of verifying "
                "integrity and compliance under the Housing Development (Control and Licensing) "
                "Act 1966 (HDA 1966) and the Construction Industry Payment and Adjudication Act "
                "2012 (CIPAA 2012). This digital signature does not replace handwritten signatures "
                "and is for Tribunal reference only."
            )
        }
        return footers.get(language, footers["ms"])


# Singleton instance
_legal_manager = None

def get_legal_manager() -> LegalMetadataManager:
    """Get or create singleton instance of LegalMetadataManager."""
    global _legal_manager
    if _legal_manager is None:
        _legal_manager = LegalMetadataManager()
    return _legal_manager
