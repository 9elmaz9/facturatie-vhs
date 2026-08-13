from __future__ import annotations

import base64
from datetime import datetime, time, timedelta
import html
from io import BytesIO
import math
import numbers
from pathlib import Path
import re
import zipfile

import pandas as pd
import streamlit as st

APP_TITLE = "Facturatie VHS"
APP_SUBTITLE = (
    "Vergelijk aanleverlijsten uit Digitalisering en MAM en maak een "
    "facturatie-overzicht per contentpartner."
)
REPOSITORY_URL = "https://github.com/9elmaz9/facturatie-vhs"
BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "assets" / "meemoo_mark_white.png"
FAVICON_PATH = BASE_DIR / "assets" / "favicon_mark.png"

DIGITALIZER_COLUMNS = {
    "pid": {"pid"},
    "duration": {"total duration of tape"},
}

MAM_COLUMNS = {
    "cp": {"cp", "content partner", "content_partner"},
    "pid": {"pid"},
    "duration": {"file_duration", "file duration"},
}

STATUS_LABELS = {
    "matched": "Gekoppeld",
    "only_in_mam": "Alleen in MAM",
    "only_in_digitalizer": "Alleen in digitalisering",
    "cp_conflict": "CP-conflict",
}

SOURCE_LABELS = {
    "digitalizer": "Digitalisering",
    "mam": "MAM",
}

ISSUE_LABELS = {
    "missing_pid": "Ontbrekende PID",
    "invalid_duration": "Ongeldige duur",
    "missing_cp": "Ontbrekende CP",
}

SUMMARY_COLUMNS = {
    "cp": "CP",
    "total_videos": "Totaal video's",
    "matched_videos": "Gekoppelde PID's",
    "only_in_mam": "Alleen in MAM",
    "total_digitalizer_duration": "Totale duur digitalisering",
    "total_mam_duration": "Totale duur MAM",
    "total_difference": "Totale afwijking",
}

SUMMARY_VISIBLE_COLUMNS = [
    "CP",
    "Totaal video's",
    "Gekoppelde PID's",
    "Alleen in MAM",
    "Totale duur digitalisering",
    "Totale duur MAM",
    "Totale afwijking",
]

DETAIL_COLUMNS = {
    "pid": "PID",
    "cp": "CP",
    "status": "Status",
    "digitalizer_duration": "Duur digitalisering",
    "mam_duration": "Duur MAM",
    "difference": "Afwijking",
    "digitalizer_video_count": "Aantal regels digitalisering",
    "mam_video_count": "Aantal regels MAM",
    "digitalizer_rows": "Rijen digitalisering",
    "mam_rows": "Rijen MAM",
}

DETAIL_VISIBLE_COLUMNS = [
    "PID",
    "CP",
    "Status",
    "Duur digitalisering",
    "Duur MAM",
    "Afwijking",
    "Aantal regels digitalisering",
    "Aantal regels MAM",
    "Rijen digitalisering",
    "Rijen MAM",
]

ISSUE_COLUMNS = {
    "source": "Bron",
    "row_number": "Rijnummer",
    "issue": "Probleem",
    "pid": "PID",
    "cp": "CP",
    "raw_duration": "Ruwe duur",
}


def normalize_header(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\n\r\t]+", " ", text)
    return re.sub(r"\s+", " ", text)


def normalize_pid(value: object) -> str:
    if pd.isna(value):
        return ""

    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return str(number).strip()

    text = str(value).strip()
    text = re.sub(r"\s+", "", text)
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", maxsplit=1)[0]
    return text


def parse_duration_to_seconds(value: object) -> int | None:
    if pd.isna(value):
        return None

    if isinstance(value, pd.Timedelta):
        return int(round(value.total_seconds()))

    if isinstance(value, timedelta):
        return int(round(value.total_seconds()))

    if isinstance(value, pd.Timestamp):
        return value.hour * 3600 + value.minute * 60 + value.second

    if isinstance(value, datetime):
        return value.hour * 3600 + value.minute * 60 + value.second

    if isinstance(value, time):
        return value.hour * 3600 + value.minute * 60 + value.second

    if isinstance(value, numbers.Number) and not isinstance(value, bool):
        number = float(value)
        if math.isnan(number):
            return None
        if abs(number) < 1:
            return int(round(number * 86400))
        return int(round(number))

    text = str(value).strip()
    if not text:
        return None

    signed = -1 if text.startswith("-") else 1
    cleaned = text.lstrip("+-").strip()

    if re.fullmatch(r"\d+(?:[.,]\d+)?", cleaned):
        cleaned_number = float(cleaned.replace(",", "."))
        if abs(cleaned_number) < 1:
            return int(round(signed * cleaned_number * 86400))
        return int(round(signed * cleaned_number))

    if ":" in cleaned:
        parts = cleaned.split(":")
        try:
            parsed = [float(part.replace(",", ".")) for part in parts]
        except ValueError:
            parsed = []

        if len(parsed) == 2:
            minutes, seconds = parsed
            return int(round(signed * (minutes * 60 + seconds)))

        if len(parsed) == 3:
            hours, minutes, seconds = parsed
            return int(round(signed * (hours * 3600 + minutes * 60 + seconds)))

        if len(parsed) == 4:
            days, hours, minutes, seconds = parsed
            return int(round(signed * (days * 86400 + hours * 3600 + minutes * 60 + seconds)))

    compact = cleaned.lower().replace(" ", "")
    match = re.fullmatch(
        r"(?:(?P<hours>\d+)h)?(?:(?P<minutes>\d+)m)?(?:(?P<seconds>\d+)s)?",
        compact,
    )
    if match and any(group is not None for group in match.groups()):
        hours = int(match.group("hours") or 0)
        minutes = int(match.group("minutes") or 0)
        seconds = int(match.group("seconds") or 0)
        return signed * (hours * 3600 + minutes * 60 + seconds)

    return None


def format_seconds(value: object) -> str:
    if pd.isna(value):
        return ""

    total_seconds = int(round(float(value)))
    sign = "-" if total_seconds < 0 else ""
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"


def count_uploaded_files(uploaded_file: object) -> int:
    return len(normalize_uploaded_files(uploaded_file))


def normalize_uploaded_files(uploaded_file: object) -> list[object]:
    if uploaded_file is None:
        return []
    if isinstance(uploaded_file, dict):
        return [uploaded_file]
    if hasattr(uploaded_file, "name"):
        return [uploaded_file]
    if isinstance(uploaded_file, (list, tuple)):
        return [file for file in uploaded_file if file is not None]
    return []


def uploaded_file_to_record(uploaded_file: object) -> dict[str, object]:
    return {
        "name": str(getattr(uploaded_file, "name", "")),
        "bytes": uploaded_file.getvalue(),
    }


def get_uploaded_file_name(uploaded_file: object) -> str:
    if isinstance(uploaded_file, dict):
        return str(uploaded_file.get("name", ""))
    return str(getattr(uploaded_file, "name", ""))


def read_excel_file(uploaded_file: object) -> pd.DataFrame:
    file_name = get_uploaded_file_name(uploaded_file) or "onbekend bestand"

    try:
        if isinstance(uploaded_file, dict):
            return pd.read_excel(BytesIO(uploaded_file["bytes"]))
        return pd.read_excel(uploaded_file)
    except ValueError as exc:
        message = str(exc).lower()
        if "worksheet index 0 is invalid" in message or "worksheets found" in message:
            raise ValueError(
                f'Bestand "{file_name}" bevat geen leesbaar werkblad. '
                "Controleer of het Excel-bestand minstens een tabblad met data heeft en "
                "sla het daarna opnieuw op als .xlsx of .xlsm."
            ) from exc
        raise
    except zipfile.BadZipFile as exc:
        if file_name.startswith("~$"):
            raise ValueError(
                f'Bestand "{file_name}" lijkt een tijdelijk Excel-lockbestand te zijn. '
                "Upload het echte Excel-bestand en niet de tijdelijke ~$.xlsx-versie."
            ) from exc
        raise ValueError(
            f'Bestand "{file_name}" is geen leesbaar Excel-bestand. '
            "Controleer of het bestand correct opent in Excel en sla het opnieuw op als .xlsx of .xlsm."
        ) from exc


def read_excel_collection(uploaded_files: list[object]) -> pd.DataFrame:
    dataframes = []
    for uploaded_file in uploaded_files:
        dataframes.append(read_excel_file(uploaded_file))
    return pd.concat(dataframes, ignore_index=True) if dataframes else pd.DataFrame()


def initialize_upload_state() -> None:
    state = st.session_state
    state.setdefault("digitalizer_files_store", [])
    state.setdefault("mam_file_store", None)
    state.setdefault("digitalizer_uploader_nonce", 0)
    state.setdefault("mam_uploader_nonce", 0)


def load_logo_base64() -> str:
    if not LOGO_PATH.exists():
        return ""
    return base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")


def find_required_columns(df: pd.DataFrame, mapping: dict[str, set[str]]) -> dict[str, str]:
    normalized_lookup = {normalize_header(column): str(column) for column in df.columns}
    resolved: dict[str, str] = {}

    for logical_name, accepted_headers in mapping.items():
        matching_column = next(
            (normalized_lookup[header] for header in accepted_headers if header in normalized_lookup),
            None,
        )
        if matching_column is None:
            expected = ", ".join(sorted(accepted_headers))
            raise ValueError(
                f"Verplichte kolom ontbreekt voor '{logical_name}'. Verwacht een van: {expected}"
            )
        resolved[logical_name] = matching_column

    return resolved


def build_input_issues(
    source_name: str,
    working_df: pd.DataFrame,
    duration_column_name: str,
    cp_column_name: str | None = None,
) -> pd.DataFrame:
    issue_rows: list[dict[str, object]] = []

    for row in working_df.itertuples(index=False):
        reasons: list[str] = []
        if not row.pid:
            reasons.append("missing_pid")
        if pd.isna(row.duration_seconds):
            reasons.append("invalid_duration")
        if cp_column_name is not None and not row.cp:
            reasons.append("missing_cp")

        if reasons:
            issue_rows.append(
                {
                    "source": source_name,
                    "row_number": row.row_number,
                    "issue": ", ".join(reasons),
                    "pid": row.pid,
                    "cp": getattr(row, "cp", ""),
                    "raw_duration": getattr(row, duration_column_name),
                }
            )

    return pd.DataFrame(issue_rows)


def prepare_digitalizer(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = find_required_columns(df, DIGITALIZER_COLUMNS)
    working = df[[columns["pid"], columns["duration"]]].copy()
    working.columns = ["pid_raw", "duration_raw"]
    working["row_number"] = working.index + 2
    working["pid"] = working["pid_raw"].apply(normalize_pid)
    working["duration_seconds"] = working["duration_raw"].apply(parse_duration_to_seconds)

    issues = build_input_issues("digitalizer", working, "duration_raw")

    valid = working[(working["pid"] != "") & working["duration_seconds"].notna()].copy()
    grouped = (
        valid.groupby("pid", as_index=False)
        .agg(
            digitalizer_duration_seconds=("duration_seconds", "sum"),
            digitalizer_video_count=("pid", "size"),
            digitalizer_rows=("row_number", lambda rows: ", ".join(str(row) for row in rows)),
        )
        .sort_values("pid")
    )
    return grouped, issues


def prepare_mam(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    columns = find_required_columns(df, MAM_COLUMNS)
    working = df[[columns["cp"], columns["pid"], columns["duration"]]].copy()
    working.columns = ["cp_raw", "pid_raw", "duration_raw"]
    working["row_number"] = working.index + 2
    working["cp"] = working["cp_raw"].fillna("").astype(str).str.strip()
    working["pid"] = working["pid_raw"].apply(normalize_pid)
    working["duration_seconds"] = working["duration_raw"].apply(parse_duration_to_seconds)

    issues = build_input_issues("mam", working, "duration_raw", cp_column_name="cp")

    valid = working[(working["pid"] != "") & working["duration_seconds"].notna()].copy()

    def collapse_cp(values: pd.Series) -> str:
        unique_values = sorted({value for value in values if value})
        if not unique_values:
            return ""
        return unique_values[0] if len(unique_values) == 1 else "MULTIPLE_CP"

    grouped = (
        valid.groupby("pid", as_index=False)
        .agg(
            cp=("cp", collapse_cp),
            mam_duration_seconds=("duration_seconds", "sum"),
            mam_video_count=("pid", "size"),
            mam_rows=("row_number", lambda rows: ", ".join(str(row) for row in rows)),
            cp_unique_count=("cp", lambda values: len({value for value in values if value})),
        )
        .sort_values("pid")
    )
    grouped["cp_conflict"] = grouped["cp_unique_count"] > 1
    return grouped, issues


def reconcile_files(digitalizer_df: pd.DataFrame, mam_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    digitalizer, digitalizer_issues = prepare_digitalizer(digitalizer_df)
    mam, mam_issues = prepare_mam(mam_df)

    details = digitalizer.merge(mam, on="pid", how="outer")
    details["status"] = "matched"
    details.loc[details["digitalizer_duration_seconds"].isna(), "status"] = "only_in_mam"
    details.loc[details["mam_duration_seconds"].isna(), "status"] = "only_in_digitalizer"
    details.loc[details["cp_conflict"].eq(True), "status"] = "cp_conflict"

    details["difference_seconds"] = (
        details["digitalizer_duration_seconds"].fillna(0) - details["mam_duration_seconds"].fillna(0)
    )
    details["cp"] = details["cp"].fillna("")

    for column in [
        "digitalizer_duration_seconds",
        "mam_duration_seconds",
        "difference_seconds",
        "digitalizer_video_count",
        "mam_video_count",
    ]:
        details[column] = pd.to_numeric(details[column], errors="coerce").astype("Int64")

    details["digitalizer_duration"] = details["digitalizer_duration_seconds"].apply(format_seconds)
    details["mam_duration"] = details["mam_duration_seconds"].apply(format_seconds)
    details["difference"] = details["difference_seconds"].apply(format_seconds)

    details = details[
        [
            "pid",
            "cp",
            "status",
            "digitalizer_duration",
            "mam_duration",
            "difference",
            "digitalizer_duration_seconds",
            "mam_duration_seconds",
            "difference_seconds",
            "digitalizer_video_count",
            "mam_video_count",
            "digitalizer_rows",
            "mam_rows",
        ]
    ].sort_values(["cp", "pid"], na_position="last")

    summary_source = details[(details["cp"] != "") & (~details["cp"].eq("MULTIPLE_CP"))].copy()
    summary = (
        summary_source.groupby("cp", as_index=False)
        .agg(
            total_videos=("pid", "count"),
            matched_videos=("status", lambda values: int((pd.Series(values) == "matched").sum())),
            only_in_mam=("status", lambda values: int((pd.Series(values) == "only_in_mam").sum())),
            total_digitalizer_seconds=("digitalizer_duration_seconds", "sum"),
            total_mam_seconds=("mam_duration_seconds", "sum"),
            total_difference_seconds=("difference_seconds", "sum"),
        )
        .sort_values("cp")
    )
    summary["total_digitalizer_duration"] = summary["total_digitalizer_seconds"].apply(format_seconds)
    summary["total_mam_duration"] = summary["total_mam_seconds"].apply(format_seconds)
    summary["total_difference"] = summary["total_difference_seconds"].apply(format_seconds)

    for column in [
        "total_videos",
        "matched_videos",
        "only_in_mam",
        "total_digitalizer_seconds",
        "total_mam_seconds",
        "total_difference_seconds",
    ]:
        summary[column] = pd.to_numeric(summary[column], errors="coerce").fillna(0).astype(int)

    summary = summary[
        [
            "cp",
            "total_videos",
            "matched_videos",
            "only_in_mam",
            "total_digitalizer_duration",
            "total_mam_duration",
            "total_difference",
            "total_digitalizer_seconds",
            "total_mam_seconds",
            "total_difference_seconds",
        ]
    ]

    mismatches = details[details["status"] != "matched"].copy()

    input_issues = pd.concat([digitalizer_issues, mam_issues], ignore_index=True)
    if input_issues.empty:
        input_issues = pd.DataFrame(columns=["source", "row_number", "issue", "pid", "cp", "raw_duration"])

    return {
        "summary": summary,
        "details": details,
        "mismatches": mismatches,
        "input_issues": input_issues,
    }


def translate_issue_text(value: object) -> str:
    if pd.isna(value) or value == "":
        return ""
    parts = [part.strip() for part in str(value).split(",")]
    return ", ".join(ISSUE_LABELS.get(part, part) for part in parts)


def build_display_frames(result: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    summary_raw = result["summary"].copy()
    summary = summary_raw.rename(columns=SUMMARY_COLUMNS).copy()
    summary = summary[SUMMARY_VISIBLE_COLUMNS]

    if not summary_raw.empty:
        total_row = pd.DataFrame(
            [
                {
                    "CP": "Totaal",
                    "Totaal video's": int(summary_raw["total_videos"].sum()),
                    "Gekoppelde PID's": int(summary_raw["matched_videos"].sum()),
                    "Alleen in MAM": int(summary_raw["only_in_mam"].sum()),
                    "Totale duur digitalisering": format_seconds(
                        summary_raw["total_digitalizer_seconds"].sum()
                    ),
                    "Totale duur MAM": format_seconds(summary_raw["total_mam_seconds"].sum()),
                    "Totale afwijking": format_seconds(
                        summary_raw["total_difference_seconds"].sum()
                    ),
                }
            ]
        )
        summary = pd.concat([summary, total_row], ignore_index=True)

    details = result["details"].copy()
    details["status"] = details["status"].map(STATUS_LABELS).fillna(details["status"])
    details = details.rename(columns=DETAIL_COLUMNS)
    details = details[DETAIL_VISIBLE_COLUMNS]

    mismatches = result["mismatches"].copy()
    mismatches["status"] = mismatches["status"].map(STATUS_LABELS).fillna(mismatches["status"])
    mismatches = mismatches.rename(columns=DETAIL_COLUMNS)
    mismatches = mismatches[DETAIL_VISIBLE_COLUMNS]

    input_issues = result["input_issues"].copy()
    if not input_issues.empty:
        input_issues["source"] = input_issues["source"].map(SOURCE_LABELS).fillna(input_issues["source"])
        input_issues["issue"] = input_issues["issue"].apply(translate_issue_text)
    input_issues = input_issues.rename(columns=ISSUE_COLUMNS)

    return {
        "summary": summary,
        "details": details,
        "mismatches": mismatches,
        "input_issues": input_issues,
    }


def to_excel_bytes(result: dict[str, pd.DataFrame]) -> bytes:
    display = build_display_frames(result)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        display["summary"].to_excel(writer, sheet_name="Overzicht per CP", index=False)
        display["details"].to_excel(writer, sheet_name="PID details", index=False)
        display["mismatches"].to_excel(writer, sheet_name="Afwijkingen", index=False)
        display["input_issues"].to_excel(writer, sheet_name="Invoerproblemen", index=False)
    buffer.seek(0)
    return buffer.getvalue()


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #f3efe6 0%, #efe7d9 100%);
            color: #213029;
        }
        .block-container {
            max-width: 1180px;
            padding-top: 2rem;
            padding-bottom: 2.5rem;
        }
        h1, h2, h3, p, li, label {
            color: #213029;
        }
        .hero-card {
            background: linear-gradient(135deg, #2bd0b7 0%, #1eae99 100%);
            border-radius: 22px;
            padding: 26px 28px;
            color: #f5f7f0;
            border: 1px solid rgba(255, 255, 255, 0.18);
            box-shadow: 0 14px 40px rgba(33, 48, 41, 0.12);
            margin-bottom: 1rem;
        }
        .hero-layout {
            display: flex;
            align-items: center;
            gap: 1.4rem;
        }
        .hero-logo-wrap {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .hero-logo {
            width: 168px;
            max-width: 100%;
            height: auto;
            display: block;
        }
        .hero-copy {
            flex: 1 1 auto;
            min-width: 0;
        }
        .hero-card h1 {
            color: #f5f7f0;
            font-size: 2.2rem;
            line-height: 1.1;
            margin: 0 0 0.75rem 0;
        }
        .hero-card p {
            color: #dff5ef;
            font-size: 1rem;
            margin: 0;
            max-width: 780px;
        }
        @media (max-width: 760px) {
            .hero-layout {
                flex-direction: column;
                align-items: flex-start;
            }
            .hero-logo-wrap {
                min-width: 0;
            }
        }
        .section-card {
            background: #fbf8f1;
            border: 1px solid #d8d0c2;
            border-radius: 18px;
            padding: 1rem 1rem 0.5rem 1rem;
            margin-bottom: 1rem;
            box-shadow: 0 10px 24px rgba(33, 48, 41, 0.05);
        }
        .section-title {
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
        }
        .section-subtitle {
            color: #6b756e;
            font-size: 0.92rem;
            margin-bottom: 0.8rem;
        }
        .uploader-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            margin-bottom: 0.25rem;
        }
        .uploader-title {
            font-weight: 700;
            font-size: 1rem;
        }
        .uploader-help {
            color: #6b756e;
            font-size: 0.88rem;
            margin-bottom: 0.8rem;
            min-height: 3.25rem;
        }
        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.36rem 0.7rem;
            font-size: 0.74rem;
            font-weight: 700;
        }
        .badge-idle {
            background: #ece5d7;
            color: #6b756e;
        }
        .badge-active {
            background: #dcefe6;
            color: #2bd0b7;
        }
        .file-selected {
            margin-top: 0.75rem;
            background: #f7f2e8;
            border: 1px solid #e2d9ca;
            border-radius: 14px;
            padding: 0.8rem 0.9rem;
        }
        .file-selected-title {
            color: #213029;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 0.5rem;
        }
        .file-selected-list {
            max-height: 132px;
            overflow-y: auto;
        }
        .file-selected-item {
            color: #4c5b54;
            font-size: 0.88rem;
            padding: 0.34rem 0;
            border-bottom: 1px solid #ebe1d2;
            word-break: break-word;
        }
        .file-selected-item:last-child {
            border-bottom: none;
            padding-bottom: 0;
        }
        .selection-note {
            color: #6b756e;
            font-size: 0.82rem;
            margin-top: 0.45rem;
        }
        div[data-testid="stMarkdownContainer"] p code,
        div[data-testid="stMarkdownContainer"] li code {
            background: #626b71;
            color: #dff5ef;
            border-radius: 8px;
            padding: 0.16rem 0.42rem;
        }
        div[data-testid="stMarkdownContainer"] pre code {
            background: transparent;
            color: inherit;
            padding: 0;
        }
        div[data-testid="stFileUploader"] {
            background: #f7f2e8;
            border: 1px dashed #d8d0c2;
            border-radius: 16px;
            padding: 0.68rem 0.95rem;
            min-height: 136px;
            display: flex !important;
            align-items: center !important;
        }
        div[data-testid="stFileUploader"] section {
            padding: 0 !important;
            min-height: 0;
            width: 100%;
            display: flex !important;
            align-items: center !important;
        }
        div[data-testid="stFileUploader"] section > div {
            width: 100%;
            display: flex !important;
            align-items: center !important;
        }
        div[data-testid="stFileUploader"] small {
            color: #6b756e;
            transform: translateY(6px);
        }
        div[data-testid="stFileUploader"] button {
            margin-left: auto !important;
            margin-right: auto !important;
            margin-top: 0 !important;
            margin-bottom: 0 !important;
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            text-align: center !important;
            min-width: 140px;
            min-height: 52px;
            padding: 0 !important;
            position: relative !important;
            background: #69716f !important;
            border-color: #69716f !important;
        }
        div[data-testid="stFileUploader"] button::after {
            content: "Upload";
            position: absolute;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #ffffff;
            font-weight: 700;
            font-size: 1rem;
            white-space: nowrap;
            pointer-events: none;
        }
        div[data-testid="stFileUploader"] button > * {
            opacity: 0 !important;
        }
        div:has(.uploader-marker.selected) + div div[data-testid="stFileUploader"] button {
            background: #dcefe6 !important;
            border-color: #dcefe6 !important;
        }
        div:has(.uploader-marker.selected) + div div[data-testid="stFileUploader"] button::after {
            color: #2bd0b7 !important;
        }
        div:has(.uploader-marker.idle) + div div[data-testid="stFileUploader"] button {
            background: #69716f !important;
            border-color: #69716f !important;
        }
        div:has(.uploader-marker.idle) + div div[data-testid="stFileUploader"] button::after {
            color: #ffffff !important;
        }
        div[data-testid="stMetric"] {
            background: #fbf8f1;
            border: 1px solid #d8d0c2;
            border-radius: 18px;
            padding: 0.55rem 0.8rem;
            box-shadow: 0 10px 24px rgba(33, 48, 41, 0.05);
        }
        div[data-testid="stMetric"] label {
            color: #6b756e;
            font-weight: 700;
        }
        div[data-testid="stMetricValue"] {
            color: #213029;
        }
        .stDownloadButton button,
        .stButton button {
            background: #2bd0b7;
            color: white;
            border: none;
            border-radius: 14px;
            padding: 0.78rem 1rem;
            font-weight: 700;
        }
        .stDownloadButton button:hover,
        .stButton button:hover {
            background: #22b6a0;
            color: white;
        }
        div[data-baseweb="tab-list"] {
            gap: 0.55rem;
        }
        button[data-baseweb="tab"] {
            background: #ece5d7;
            border-radius: 14px 14px 0 0;
            color: #213029;
            border: none;
            padding: 0.65rem 0.95rem;
            font-weight: 700;
        }
        button[data-baseweb="tab"][aria-selected="true"] {
            background: #2bd0b7;
            color: white;
        }
        div[data-testid="stDataFrame"] {
            background: #fbf8f1;
            border: 1px solid #d8d0c2;
            border-radius: 18px;
            padding: 0.25rem;
            box-shadow: 0 10px 24px rgba(33, 48, 41, 0.05);
        }
        div[data-testid="stExpander"] {
            background: #fbf8f1;
            border: 1px solid #d8d0c2;
            border-radius: 18px;
            overflow: hidden;
        }
        div[data-testid="stExpander"] details summary {
            background: #69716f;
            border-radius: 16px 16px 0 0;
            transition: background 0.2s ease;
        }
        div[data-testid="stExpander"] details summary:hover {
            background: #747c7a;
        }
        div[data-testid="stExpander"] details[open] summary {
            border-bottom: 1px solid #d8d0c2;
        }
        div[data-testid="stExpander"] details summary p {
            color: #f5f7f0 !important;
            font-weight: 700;
        }
        div[data-testid="stExpander"] details summary svg {
            fill: #dff5ef !important;
        }
        .schema-help-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 0.7rem;
            color: #213029;
        }
        .schema-help-list {
            margin: 0 0 1rem 1.2rem;
            padding: 0;
        }
        .schema-help-list li {
            margin-bottom: 0.65rem;
        }
        .schema-link-row {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            color: #4c5b54;
            font-size: 0.96rem;
        }
        .schema-link-row svg {
            width: 18px;
            height: 18px;
            fill: #4c5b54;
            flex: 0 0 auto;
        }
        .schema-link-row a {
            color: #1e7f72;
            font-weight: 700;
            text-decoration: none;
        }
        .schema-link-row a:hover {
            text-decoration: underline;
        }
        .session-warning {
            margin: 0.45rem 0 1rem 0;
            background: #fff6c7;
            border: 1px solid #eadf9d;
            border-radius: 14px;
            color: #5a5230;
            padding: 0.8rem 0.95rem;
            font-size: 0.92rem;
            box-shadow: 0 8px 18px rgba(33, 48, 41, 0.04);
        }
        .session-warning strong {
            color: #4e4727;
        }
        .completion-banner {
            display: flex;
            align-items: flex-start;
            gap: 0.85rem;
            margin: 0.55rem 0 1rem 0;
            background: linear-gradient(135deg, #2bd0b7 0%, #1eae99 100%);
            border: 1px solid rgba(255, 255, 255, 0.18);
            border-radius: 18px;
            color: #f5f7f0;
            padding: 0.95rem 1rem;
            box-shadow: 0 10px 24px rgba(33, 48, 41, 0.08);
        }
        .completion-banner-icon {
            width: 30px;
            height: 30px;
            border-radius: 999px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: rgba(255, 255, 255, 0.18);
            color: #ffffff;
            font-weight: 800;
            flex: 0 0 auto;
        }
        .completion-banner-title {
            font-size: 1rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.15rem;
        }
        .completion-banner-text {
            color: #dff5ef;
            font-size: 0.92rem;
            line-height: 1.45;
        }
        div[data-testid="stAlert"] {
            border-radius: 16px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    logo_markup = ""
    logo_base64 = load_logo_base64()
    if logo_base64:
        logo_markup = (
            "<div class='hero-logo-wrap'>"
            f"<img class='hero-logo' src='data:image/png;base64,{logo_base64}' alt='meemoo logo'>"
            "</div>"
        )

    st.markdown(
        f"""
        <section class="hero-card">
            <div class="hero-layout">
                {logo_markup}
                <div class="hero-copy">
                    <h1>{APP_TITLE}</h1>
                    <p>{APP_SUBTITLE}</p>
                </div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_section_intro(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="section-title">{title}</div>
            <div class="section-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_uploader_card(title: str, help_text: str, uploaded_file: object) -> None:
    selected_count = count_uploaded_files(uploaded_file)
    is_selected = selected_count > 0
    badge_class = "badge-active" if is_selected else "badge-idle"
    badge_text = (
        f"{selected_count} geselecteerd" if is_selected and selected_count > 1
        else "Geselecteerd" if is_selected
        else "Niet geselecteerd"
    )
    st.markdown(
        f"""
        <div class="uploader-title-row">
            <div class="uploader-title">{title}</div>
            <span class="badge {badge_class}">{badge_text}</span>
        </div>
        <div class="uploader-help">{help_text}</div>
        """,
        unsafe_allow_html=True,
    )


def render_uploader_marker(uploaded_file: object) -> None:
    selected_class = "selected" if count_uploaded_files(uploaded_file) > 0 else "idle"
    st.markdown(
        f"<div class='uploader-marker {selected_class}'></div>",
        unsafe_allow_html=True,
    )


def render_selected_file(uploaded_file: object) -> None:
    uploaded_files = normalize_uploaded_files(uploaded_file)
    if not uploaded_files:
        return

    names = [html.escape(get_uploaded_file_name(uploaded_file)) for uploaded_file in uploaded_files]
    heading = (
        f"{len(uploaded_files)} bestanden klaar voor verwerking"
        if len(uploaded_files) > 1
        else f"Bestand: {names[0]}"
    )
    items_markup = "".join(
        f"<div class='file-selected-item'>{name}</div>"
        for name in names
    )
    note = (
        "<div class='selection-note'>Nieuwe upload vervangt de huidige selectie.</div>"
    )
    st.markdown(
        (
            "<div class='file-selected'>"
            f"<div class='file-selected-title'>{heading}</div>"
            f"<div class='file-selected-list'>{items_markup}</div>"
            f"{note}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def show_schema_help() -> None:
    github_icon = (
        '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">'
        '<path d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38 '
        '0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52 '
        '-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2 '
        '-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 '
        '7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 '
        '2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 '
        '0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"></path>'
        "</svg>"
    )
    st.markdown(
        f"""
        <div class="schema-help">
            <div class="schema-help-title">Benodigde kolommen</div>
            <ul class="schema-help-list">
                <li>Digitalisering: <code>PID</code>, <code>Total duration of tape</code></li>
                <li>MAM: <code>CP</code>, <code>PID</code>, <code>file_duration</code></li>
            </ul>
            <div class="schema-link-row">
                {github_icon}
                <span>Volledige toelichting en README:</span>
                <a href="{REPOSITORY_URL}" target="_blank" rel="noopener noreferrer">GitHub-repository</a>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_refresh_warning(has_session_data: bool) -> None:
    is_enabled = "true" if has_session_data else "false"
    st.html(
        f"""
        <div style="display:none"></div>
        <script>
        (() => {{
            const enabled = {is_enabled};
            const handlerKey = "__facturatieBeforeUnloadHandler";

            if (window[handlerKey]) {{
                window.removeEventListener("beforeunload", window[handlerKey]);
                delete window[handlerKey];
            }}

            if (!enabled) {{
                return;
            }}

            const handler = function(event) {{
                event.preventDefault();
                event.returnValue = "";
            }};

            window.addEventListener("beforeunload", handler);
            window[handlerKey] = handler;
        }})();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def render_session_warning(has_session_data: bool) -> None:
    if not has_session_data:
        return

    st.markdown(
        """
        <div class="session-warning">
            <strong>Opgelet:</strong> bij refresh of sluiten van de pagina gaat de huidige sessie verloren.
            Download het resultaat eerst indien nodig.
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_completion_banner(has_issues: bool) -> None:
    subtitle = (
        "Controleer de tabs Afwijkingen en Invoerproblemen."
        if has_issues
        else "Geen afwijkingen of invoerproblemen gevonden."
    )
    st.markdown(
        f"""
        <div class="completion-banner">
            <div class="completion-banner-icon">✓</div>
            <div>
                <div class="completion-banner-title">Verwerking voltooid</div>
                <div class="completion-banner-text">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    page_icon = str(FAVICON_PATH) if FAVICON_PATH.exists() else None
    st.set_page_config(page_title=APP_TITLE, page_icon=page_icon, layout="wide")
    initialize_upload_state()
    apply_theme()
    render_header()

    with st.expander("Kolommen", expanded=False):
        show_schema_help()

    render_section_intro(
        "Bestanden opladen",
        "Laad de aanleverlijsten uit Digitalisering en MAM op.",
    )

    upload_shell_left, upload_center, upload_shell_right = st.columns([0.04, 0.92, 0.04])
    with upload_center:
        left_column, right_column = st.columns(2, gap="large")

    with left_column:
        digitalizer_stored_files = st.session_state["digitalizer_files_store"]
        render_uploader_card(
            "Digitalisering",
            "Upload een of meerdere aanleverlijsten uit Digitalisering.",
            digitalizer_stored_files,
        )
        render_uploader_marker(digitalizer_stored_files)
        digitalizer_files = st.file_uploader(
            "Digitalisering Excel",
            type=["xlsx", "xlsm"],
            key=f"digitalizer_{st.session_state['digitalizer_uploader_nonce']}",
            label_visibility="collapsed",
            accept_multiple_files=True,
        )
        if digitalizer_files:
            st.session_state["digitalizer_files_store"] = [
                uploaded_file_to_record(uploaded_file)
                for uploaded_file in digitalizer_files
            ]
            st.session_state["digitalizer_uploader_nonce"] += 1
            st.rerun()
        render_selected_file(digitalizer_stored_files)
        if digitalizer_stored_files and st.button("Wis selectie", key="clear_digitalizer"):
            st.session_state["digitalizer_files_store"] = []
            st.rerun()

    with right_column:
        mam_stored_file = st.session_state["mam_file_store"]
        render_uploader_card(
            "MAM",
            "Upload de aanleverlijst uit MAM.",
            mam_stored_file,
        )
        render_uploader_marker(mam_stored_file)
        mam_file = st.file_uploader(
            "MAM Excel",
            type=["xlsx", "xlsm"],
            key=f"mam_{st.session_state['mam_uploader_nonce']}",
            label_visibility="collapsed",
        )
        if mam_file is not None:
            st.session_state["mam_file_store"] = uploaded_file_to_record(mam_file)
            st.session_state["mam_uploader_nonce"] += 1
            st.rerun()
        render_selected_file(mam_stored_file)
        if mam_stored_file and st.button("Wis selectie", key="clear_mam"):
            st.session_state["mam_file_store"] = None
            st.rerun()

    digitalizer_stored_files = st.session_state["digitalizer_files_store"]
    mam_stored_file = st.session_state["mam_file_store"]
    has_session_data = bool(digitalizer_stored_files or mam_stored_file)
    render_refresh_warning(has_session_data)
    render_session_warning(has_session_data)

    if not digitalizer_stored_files or not mam_stored_file:
        st.info("Laad minstens een aanleverlijst uit Digitalisering en een uit MAM op.")
        return

    try:
        digitalizer_df = read_excel_collection(digitalizer_stored_files)
        mam_df = read_excel_collection([mam_stored_file])
        result = reconcile_files(digitalizer_df, mam_df)
    except Exception as exc:  # pragma: no cover
        st.error(str(exc))
        return

    display = build_display_frames(result)
    summary = display["summary"]
    details = display["details"]
    mismatches = display["mismatches"]
    input_issues = display["input_issues"]

    total_cp = int(result["summary"]["cp"].nunique()) if not result["summary"].empty else 0
    matched_count = int((result["details"]["status"] == "matched").sum())
    total_difference = (
        format_seconds(result["summary"]["total_difference_seconds"].sum())
        if not result["summary"].empty
        else "00:00:00"
    )
    total_digitalizer_duration = (
        format_seconds(result["summary"]["total_digitalizer_seconds"].sum())
        if not result["summary"].empty
        else "00:00:00"
    )

    render_completion_banner(
        has_issues=not (result["mismatches"].empty and result["input_issues"].empty)
    )

    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    metric_one.metric("Aantal CP's", total_cp)
    metric_two.metric("Gekoppelde PID's", matched_count)
    metric_three.metric("Totale duur digitalisering", total_digitalizer_duration)
    metric_four.metric("Totale afwijking", total_difference)

    render_section_intro(
        "Overzicht per contentpartner",
        "Gebruik dit overzicht rechtstreeks als basis voor controle en facturatie.",
    )
    st.dataframe(summary, width="stretch", hide_index=True)

    st.download_button(
        "Download Excel-resultaat",
        data=to_excel_bytes(result),
        file_name="facturatie_vhs_resultaat.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    render_section_intro(
        "Controle en detail",
        "Bekijk per PID waar de bronbestanden overeenkomen en waar opvolging nodig is.",
    )
    tab_details, tab_mismatches, tab_issues = st.tabs(
        ["PID-details", "Afwijkingen", "Invoerproblemen"]
    )

    with tab_details:
        st.dataframe(details, width="stretch", hide_index=True)

    with tab_mismatches:
        st.dataframe(mismatches, width="stretch", hide_index=True)

    with tab_issues:
        st.dataframe(input_issues, width="stretch", hide_index=True)


if __name__ == "__main__":
    main()
