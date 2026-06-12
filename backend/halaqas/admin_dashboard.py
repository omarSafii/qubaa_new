import csv
from collections import Counter
from datetime import datetime, time, timedelta
from urllib.parse import urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, F, IntegerField, ExpressionWrapper, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from students.models import MemorizationRecord, Student

from .models import Attendance, Category, Halaqa, HalaqaMembership, Homework, Plan, PointTransaction, Session, Teacher
from .views import _build_homework_snapshot

PANEL_EXPORT_REPORT_MAP = {
    "overviewPanel": "executive_summary",
    "halaqasPanel": "halaqa_reports",
    "studentsPanel": "student_reports",
    "plansPanel": "plan_followup",
    "attendancePanel": "attendance_risk",
    "homeworkPanel": "homework_pending",
    "reportsPanel": "reports_bundle",
}
EXPORT_REPORT_OPTIONS = [
    {
        "value": "current_view",
        "label": "Ø§Ù„Ø¹Ø±Ø¶ Ø§Ù„Ø­Ø§Ù„ÙŠ",
        "description": "ÙŠÙˆØ§ÙÙ‚ Ø§Ù„Ù‚Ø³Ù… Ø§Ù„Ù…ÙØªÙˆØ­ Ø­Ø§Ù„ÙŠØ§ ÙÙŠ Ø§Ù„Ù„ÙˆØ­Ø©",
    },
    {
        "value": "executive_summary",
        "label": "Ø§Ù„Ù…Ù„Ø®Øµ Ø§Ù„ØªÙ†ÙÙŠØ°ÙŠ",
        "description": "Ù…Ù„Ø®Øµ Ø¥Ø¯Ø§Ø±ÙŠ Ù…Ø¹ Ø§Ù„Ù…Ø¤Ø´Ø±Ø§Øª ÙˆØ§Ù„ØªÙ†Ø¨ÙŠÙ‡Ø§Øª",
    },
    {
        "value": "category_reports",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„ÙØ¦Ø§Øª",
        "description": "ØªØ±ØªÙŠØ¨Ø§Øª Ø§Ù„ÙØ¦Ø§Øª ÙˆØ§Ù„Ø­Ø§Ù„Ø§Øª ØºÙŠØ± Ø§Ù„Ù…Ø­Ø³ÙˆÙ…Ø©",
    },
    {
        "value": "halaqa_reports",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„Ø­Ù„Ù‚Ø§Øª",
        "description": "Ù‚ÙˆØ© Ø§Ù„Ø­Ù„Ù‚Ø§Øª ÙˆÙ…Ù„Ø®Øµ Ø§Ù„Ø£Ø¯Ø§Ø¡ Ø§Ù„Ø¥Ø´Ø±Ø§ÙÙŠ",
    },
    {
        "value": "student_reports",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„Ø·Ù„Ø§Ø¨",
        "description": "Ø¨Ø·Ø§Ù‚Ø§Øª Ø§Ù„Ø·Ù„Ø§Ø¨ Ø§Ù„Ø¥Ø´Ø±Ø§ÙÙŠØ© ÙˆØ§Ù„Ø­Ø§Ù„Ø§Øª Ø§Ù„Ø­Ø±Ø¬Ø©",
    },
    {
        "value": "plan_followup",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„Ø®Ø·Ø·",
        "description": "Ø§Ù„Ø·Ù„Ø§Ø¨ Ø§Ù„Ù…ØªØ£Ø®Ø±ÙˆÙ† Ø¹Ù„Ù‰ Ø§Ù„Ø®Ø·Ø· ÙˆØ§Ù„Ù…Ø´Ù…ÙˆÙ„ÙˆÙ† Ø¨Ù‡Ø§",
    },
    {
        "value": "attendance_risk",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„Ø­Ø¶ÙˆØ±",
        "description": "Ø§Ù„Ø­Ø¶ÙˆØ± Ø§Ù„Ø¶Ø¹ÙŠÙ ÙˆØ§Ù„Ø­Ø§Ù„Ø§Øª Ø§Ù„ØªÙŠ ØªØ­ØªØ§Ø¬ Ù…ØªØ§Ø¨Ø¹Ø©",
    },
    {
        "value": "homework_pending",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„ÙˆØ§Ø¬Ø¨",
        "description": "Ø§Ù„ÙˆØ§Ø¬Ø¨Ø§Øª Ø§Ù„Ù…Ø¹Ù„Ù‚Ø© ÙˆØ§Ù„ØªÙƒÙ„ÙŠÙØ§Øª Ø§Ù„Ù†Ø´Ø·Ø©",
    },
    {
        "value": "points_reports",
        "label": "ØªÙ‚Ø§Ø±ÙŠØ± Ø§Ù„Ù†Ù‚Ø§Ø·",
        "description": "ØªØ±ØªÙŠØ¨ Ø§Ù„Ù†Ù‚Ø§Ø· ÙˆØ£Ø­Ø¯Ø« Ø§Ù„Ø­Ø±ÙƒØ§Øª",
    },
    {
        "value": "reports_bundle",
        "label": "Ø§Ù„ØªÙ‚Ø±ÙŠØ± Ø§Ù„Ù…Ø¬Ù…Ø¹",
        "description": "Ø£Ù‡Ù… ØªØ±ØªÙŠØ¨Ø§Øª Ø§Ù„ÙØ¦Ø§Øª ÙˆØ§Ù„Ø­Ù„Ù‚Ø§Øª ÙˆØ§Ù„Ù…Ø®Ø§Ø·Ø±",
    },
]
EXPORT_LEVEL_OPTIONS = [
    {
        "value": "summary",
        "label": "Ù…Ù„Ø®Øµ",
        "description": "Ù…Ø¤Ø´Ø±Ø§Øª Ø±Ø¦ÙŠØ³ÙŠØ© ÙˆØ¬Ø¯Ø§ÙˆÙ„ Ù…Ø®ØªØµØ±Ø©",
    },
    {
        "value": "detailed",
        "label": "ØªÙØµÙŠÙ„ÙŠ",
        "description": "Ø¨ÙŠØ§Ù†Ø§Øª Ø¬Ø¯ÙˆÙ„ÙŠØ© Ø£ÙƒØ«Ø± Ø´Ù…ÙˆÙ„Ø§ Ù„Ù„Ù…ØªØ§Ø¨Ø¹Ø©",
    },
]


VERSE_COUNT_EXPR = ExpressionWrapper(
    F("to_verse") - F("from_verse") + Value(1),
    output_field=IntegerField(),
)
UNRESOLVED_CATEGORY_FILTER = "__unresolved__"
UNRESOLVED_CATEGORY_LABEL = "غير مصنف رسميًا"


def _infer_category(grade):
    if hasattr(grade, "category_id") and getattr(grade, "category_id", None):
        return grade.category.name
    return UNRESOLVED_CATEGORY_LABEL


def _range_days(range_key):
    return {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "year": 365,
    }.get(range_key, 30)


def _date_bounds(range_key):
    today = timezone.localdate()
    days = _range_days(range_key)
    return today - timedelta(days=days - 1), today


def _parse_local_date(raw_value):
    if not raw_value:
        return None
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _resolve_date_window(range_key, start_raw="", end_raw=""):
    parsed_start = _parse_local_date(start_raw)
    parsed_end = _parse_local_date(end_raw)

    if range_key == "custom" or parsed_start or parsed_end:
        resolved_end = parsed_end or timezone.localdate()
        resolved_start = parsed_start or (resolved_end - timedelta(days=_range_days("30d") - 1))
        if resolved_start > resolved_end:
            resolved_start, resolved_end = resolved_end, resolved_start
        return resolved_start, resolved_end, "custom"

    start_date, end_date = _date_bounds(range_key)
    return start_date, end_date, range_key


def _format_date_window_label(start_date, end_date):
    return f"{start_date:%Y-%m-%d} - {end_date:%Y-%m-%d}"


def _build_fallback_series(labels, values):
    return {
        "labels": labels,
        "values": values,
        "is_demo": True,
    }


def _format_day_label(day_value):
    return day_value.strftime("%d/%m")


def _as_local_midnight(date_value):
    return timezone.make_aware(
        datetime.combine(date_value, time.min),
        timezone.get_current_timezone(),
    )


def _get_selected_teacher_ids(teacher_filter):
    return [int(teacher_filter)] if teacher_filter else list(
        Teacher.objects.values_list("pk", flat=True)
    )


def _resolve_attendance_rate(present, absent, excused=0):
    total_marked = present + absent + excused
    return round((present / total_marked) * 100, 1) if total_marked else 0


def _resolve_student_status(summary):
    if not summary.get("halaqa_id"):
        return "unassigned"
    if summary["attendance_rate"] < 75 or not summary["category_resolved"]:
        return "attention"
    return "active"


def _dashboard_url(base_url, active_filters, *, overrides=None, fragment=""):
    params = {
        key: value
        for key, value in active_filters.items()
        if value not in ("", None)
    }
    for key, value in (overrides or {}).items():
        if value in ("", None):
            params.pop(key, None)
        else:
            params[key] = str(value)

    query_string = urlencode(params)
    url = f"{base_url}?{query_string}" if query_string else base_url
    return f"{url}#{fragment}" if fragment else url


def _collect_notes(*candidates):
    notes = []
    for candidate in candidates:
        note_text = (candidate or "").strip()
        if note_text and note_text not in notes:
            notes.append(note_text)
    return notes


def _status_tone(value, mapping, default="info"):
    return mapping.get(value, default)


def _resolve_category_snapshot(student, membership=None):
    halaqa = membership.halaqa if membership is not None else getattr(student, "halaqa", None)
    category = None
    if getattr(student, "category_id", None):
        category = student.category
    elif halaqa is not None and getattr(halaqa, "category_id", None):
        category = halaqa.category

    if category is not None:
        return {
            "id": str(category.id),
            "code": category.code,
            "name": category.name,
            "resolved": True,
            "hint": "",
        }

    inferred_hint = Category.infer_name_from_grade(getattr(student, "grade", ""))
    if inferred_hint == "غير مصنف":
        inferred_hint = ""
    return {
        "id": UNRESOLVED_CATEGORY_FILTER,
        "code": UNRESOLVED_CATEGORY_FILTER,
        "name": UNRESOLVED_CATEGORY_LABEL,
        "resolved": False,
        "hint": inferred_hint,
    }


def _resolve_halaqa_strength_score(row):
    student_count = max(row["student_count"], 1)
    memorization_score = min((row["memorized_in_range"] / student_count) * 8, 100)
    points_score = min((max(row["points_in_range"], 0) / student_count) * 12, 100)
    plan_score = (row["active_plan_students"] / student_count) * 100
    homework_total = row["pending_homework_students"] + row["evaluated_homework_students"]
    homework_score = (
        (row["evaluated_homework_students"] / homework_total) * 100
        if homework_total
        else 100
    )
    followup_penalty = (row["followup_students"] / student_count) * 35
    raw_score = (
        (row["attendance_rate"] * 0.45)
        + (memorization_score * 0.20)
        + (points_score * 0.15)
        + (plan_score * 0.10)
        + (homework_score * 0.10)
        - followup_penalty
    )
    return round(max(0, min(raw_score, 100)), 1)


def _resolve_halaqa_strength_tone(score):
    if score >= 80:
        return "success"
    if score >= 60:
        return "warning"
    return "danger"


def _describe_attendance_trend(entries):
    if not entries:
        return "لا توجد سجلات حضور", "info"
    latest_entry = entries[-1]
    latest_rate = latest_entry["rate"]
    if len(entries) == 1:
        return f"آخر جلسة {latest_rate}% حضور", "info"

    previous_rate = entries[-2]["rate"]
    delta = round(latest_rate - previous_rate, 1)
    if delta >= 5:
        return f"تحسن بمقدار {delta}% في آخر جلستين", "success"
    if delta <= -5:
        return f"تراجع بمقدار {abs(delta)}% في آخر جلستين", "danger"
    return f"مستقر حول {latest_rate}% في آخر جلستين", "warning"


def _resolve_halaqa_signal(*, attendance_rate, pending_homework, followup_students, points_delta):
    if attendance_rate >= 85 and pending_homework <= 1 and followup_students == 0:
        return "مستقرة", "success"
    if attendance_rate >= 70 and pending_homework <= 3 and followup_students <= 2 and points_delta >= 0:
        return "تحت المراقبة", "warning"
    return "تحتاج تدخلا", "danger"


def _get_export_report_options():
    return [
        {
            "value": "current_view",
            "label": "العرض الحالي",
            "description": "يطابق القسم المفتوح حاليا في لوحة الإدارة",
        },
        {
            "value": "executive_summary",
            "label": "الملخص التنفيذي",
            "description": "مؤشرات الإدارة والتنبيهات الرئيسية",
        },
        {
            "value": "category_reports",
            "label": "تقارير الفئات",
            "description": "ترتيبات الفئات والحالات غير المحسومة",
        },
        {
            "value": "halaqa_reports",
            "label": "تقارير الحلقات",
            "description": "ملخصات الحلقات وأقواها وأضعفها",
        },
        {
            "value": "student_reports",
            "label": "تقارير الطلاب",
            "description": "بطاقات الطلاب الإشرافية والحالات الحرجة",
        },
        {
            "value": "plan_followup",
            "label": "تقارير الخطط",
            "description": "الطلاب المتأخرون على الخطط والمتابعة",
        },
        {
            "value": "attendance_risk",
            "label": "تقارير الحضور",
            "description": "ضعف الحضور والحالات التي تحتاج تدخلا",
        },
        {
            "value": "homework_pending",
            "label": "تقارير الواجب",
            "description": "الواجبات المعلقة والنشطة",
        },
        {
            "value": "points_reports",
            "label": "تقارير النقاط",
            "description": "ترتيب النقاط وأحدث الحركات",
        },
        {
            "value": "reports_bundle",
            "label": "التقرير المجمع",
            "description": "أهم ترتيبات الفئات والحلقات والمخاطر",
        },
    ]


def _get_export_level_options():
    return [
        {
            "value": "summary",
            "label": "ملخص",
            "description": "مؤشرات رئيسية وجداول مختصرة",
        },
        {
            "value": "detailed",
            "label": "تفصيلي",
            "description": "بيانات جدولية أوسع للمتابعة الإدارية",
        },
    ]


def _resolve_export_report_key(report_key, current_panel):
    valid_keys = {option["value"] for option in _get_export_report_options() if option["value"] != "current_view"}
    if report_key == "current_view":
        return PANEL_EXPORT_REPORT_MAP.get(current_panel, "executive_summary")
    if report_key in valid_keys:
        return report_key
    return "executive_summary"


def _display_export_value(value):
    if value in (None, ""):
        return "—"
    if isinstance(value, bool):
        return "نعم" if value else "لا"
    return str(value)


def _build_export_scope_rows(context, report_label, level_label):
    filters = context["filters"]
    category_map = {
        option["value"]: option["label"]
        for option in context["filter_options"]["categories"]
    }
    halaqa_map = {
        str(halaqa.id): halaqa.name
        for halaqa in context["filter_options"]["halaqas"]
    }
    teacher_map = {
        str(teacher.pk): teacher.full_name
        for teacher in context["filter_options"]["teachers"]
    }
    student_map = {
        option["value"]: option["label"]
        for option in context["filter_options"]["students"]
    }
    status_map = {
        "all": "كل الحالات",
        "active": "نشط",
        "attention": "يحتاج متابعة",
        "unassigned": "غير مسند",
    }
    return [
        {
            "label": "نطاق الإشراف",
            "value": context["page_subtitle"],
            "detail": "يعكس الفلاتر الحالية كما تظهر في لوحة الإدارة.",
        },
        {
            "label": "الفترة الزمنية",
            "value": context["date_window_label"],
            "detail": "جميع المؤشرات والترتيبات مقيدة بهذا النطاق عندما ينطبق ذلك.",
        },
        {
            "label": "نوع التقرير",
            "value": report_label,
            "detail": f"مستوى البيانات: {level_label}",
        },
        {
            "label": "الفئة",
            "value": category_map.get(filters["category"], "كل الفئات"),
            "detail": "تدعم الفئات غير المحسومة خيارا مستقلا للمتابعة.",
        },
        {
            "label": "الحلقة",
            "value": halaqa_map.get(filters["halaqa"], "كل الحلقات"),
            "detail": f"المعلم: {teacher_map.get(filters['teacher'], 'كل المعلمين')}",
        },
        {
            "label": "الطالب",
            "value": student_map.get(filters["student"], "كل الطلاب"),
            "detail": f"حالة التركيز: {status_map.get(filters['status'], 'كل الحالات')}",
        },
    ]


def _build_export_table(title, columns, rows, empty_message):
    return {
        "title": title,
        "columns": columns,
        "rows": rows,
        "empty_message": empty_message,
    }


def _build_admin_dashboard_export_package(context, report_key):
    student_rows = list(context["student_supervision_rows"])
    halaqa_rows = list(context["halaqa_supervision_rows"])
    category_rows = list(context["category_supervision_rows"])
    top_students_rows = sorted(
        student_rows,
        key=lambda item: (item["points_total"], item["memorized_total"]),
        reverse=True,
    )
    points_leaderboard_rows = top_students_rows
    weak_attendance_rows = sorted(
        [
            row
            for row in student_rows
            if row["attendance_rate"] < 75 or row["status"] == "attention"
        ],
        key=lambda item: (item["attendance_rate"], item["points_total"], item["name"]),
    )
    plan_followup_rows = sorted(
        [
            row
            for row in student_rows
            if row["halaqa_id"] and (
                not row["plan"]
                or row["attendance_rate"] < 75
                or (
                    row["last_memorization"]
                    and row["last_memorization"].evaluation == "needs_followup"
                )
            )
        ],
        key=lambda item: (
            0 if not item["plan"] else 1,
            item["attendance_rate"],
            item["points_total"],
            item["name"],
        ),
    )
    students_with_active_plans_rows = sorted(
        [row for row in student_rows if row["plan"] or row["active_plans"]],
        key=lambda item: (item["active_plans"], item["attendance_rate"], item["points_total"]),
        reverse=True,
    )
    pending_homework_rows = sorted(
        [row for row in student_rows if row["homework_status"] in {"assigned", "pending"}],
        key=lambda item: (item["attendance_rate"], item["name"]),
    )
    homework_visible_rows = sorted(
        [row for row in student_rows if row["homework_status"] != "none"],
        key=lambda item: (item["halaqa_name"], item["name"]),
    )
    at_risk_rows = [row for row in student_rows if row["at_risk"]]
    strongest_halaqa_rows = sorted(
        halaqa_rows,
        key=lambda item: (-item["strength_score"], -item["attendance_rate"], item["name"]),
    )
    weakest_halaqa_rows = sorted(
        halaqa_rows,
        key=lambda item: (item["strength_score"], item["attendance_rate"], item["name"]),
    )
    category_attendance_rows = sorted(
        category_rows,
        key=lambda item: (-item["attendance_rate"], -item["student_count"], item["name"]),
    )
    category_memorization_rows = sorted(
        category_rows,
        key=lambda item: (-item["memorized_in_range"], -item["memorized_total"], item["name"]),
    )
    category_points_rows = sorted(
        category_rows,
        key=lambda item: (-item["points_in_range"], -item["points_total"], item["name"]),
    )
    unresolved_rows = [
        [
            "طالب",
            row["name"],
            row["halaqa_name"],
            row["followup_summary"],
            row["category_hint"] or "لا توجد قرينة مباشرة",
        ]
        for row in student_rows
        if not row["category_resolved"]
    ]
    unresolved_rows.extend(
        [
            "حلقة",
            row["name"],
            row["teacher_names"],
            "لم تربط بعد بفئة رسمية",
            "راجع ربط الحلقة بفئة معتمدة",
        ]
        for row in halaqa_rows
        if not row["category_resolved"]
    )

    def card(label, value, detail=""):
        return {
            "label": label,
            "value": _display_export_value(value),
            "detail": detail,
        }

    alerts_table = _build_export_table(
        "التنبيهات الإدارية",
        ["العنوان", "العدد", "التفصيل", "الأولوية"],
        [
            [alert["title"], _display_export_value(alert["count"]), alert["detail"], alert["tone"]]
            for alert in context["alerts"]
        ],
        "لا توجد تنبيهات ظاهرة ضمن هذا النطاق.",
    )
    latest_registrations_table = _build_export_table(
        "أحدث التسجيلات",
        ["الطالب", "الصف", "الحلقة", "ولي الأمر", "الحالة"],
        [
            [row["name"], row["grade"], row["halaqa_name"], row["parent_name"], row["status"]]
            for row in context["latest_registrations"]
        ],
        "لا توجد تسجيلات حديثة ضمن هذا النطاق.",
    )
    category_attendance_table = _build_export_table(
        "الفئات الأعلى حضورا",
        ["الفئة", "نسبة الحضور", "الطلاب", "الحلقات", "حالات المتابعة"],
        [
            [row["name"], row["attendance_rate"], row["student_count"], row["halaqa_count"], row["followup_students"]]
            for row in category_attendance_rows
        ],
        "لا توجد بيانات حضور كافية بحسب الفئات.",
    )
    category_memorization_table = _build_export_table(
        "الفئات الأعلى حفظا",
        ["الفئة", "الحفظ في الفترة", "إجمالي الحفظ", "معدل لكل طالب", "خطط نشطة"],
        [
            [row["name"], row["memorized_in_range"], row["memorized_total"], row["memorization_per_student"], row["active_plan_students"]]
            for row in category_memorization_rows
        ],
        "لا توجد تسجيلات حفظ كافية بحسب الفئات.",
    )
    category_points_table = _build_export_table(
        "الفئات الأعلى نقاطا",
        ["الفئة", "نقاط الفترة", "الرصيد الكلي", "معدل لكل طالب", "واجبات معلقة"],
        [
            [row["name"], row["points_in_range"], row["points_total"], row["points_per_student"], row["pending_homework_students"]]
            for row in category_points_rows
        ],
        "لا توجد حركات نقاط كافية بحسب الفئات.",
    )
    category_summary_table = _build_export_table(
        "ملخص الفئات",
        ["الفئة", "الطلاب", "الحلقات", "الحضور", "الخطط", "معلق", "متابعة", "غير محسوم"],
        [
            [
                row["name"],
                row["student_count"],
                row["halaqa_count"],
                row["attendance_rate"],
                row["active_plan_students"],
                row["pending_homework_students"],
                row["followup_students"],
                f"طلاب {row['unresolved_students']} | حلقات {row['unresolved_halaqas']}",
            ]
            for row in category_rows
        ],
        "لا توجد فئات ظاهرة ضمن هذا النطاق.",
    )
    unresolved_table = _build_export_table(
        "حالات تصنيف غير محسومة",
        ["النوع", "الاسم", "السياق", "التفصيل", "القرينة"],
        unresolved_rows,
        "كل الكيانات الظاهرة مربوطة بفئات رسمية واضحة.",
    )
    halaqa_summary_table = _build_export_table(
        "ملخص الحلقات",
        ["الحلقة", "الفئة", "المعلمون", "الطلاب", "الحضور", "الحفظ", "النقاط", "الإشارة"],
        [
            [row["name"], row["category_name"], row["teacher_names"], row["student_count"], row["attendance_rate"], row["memorized_in_range"], row["points_in_range"], row["signal_label"]]
            for row in halaqa_rows
        ],
        "لا توجد حلقات مرئية ضمن هذا النطاق.",
    )
    strongest_halaqas_table = _build_export_table(
        "أقوى الحلقات",
        ["الحلقة", "الفئة", "مؤشر القوة", "الحضور", "الحفظ", "النقاط"],
        [
            [row["name"], row["category_name"], row["strength_score"], row["attendance_rate"], row["memorized_in_range"], row["points_in_range"]]
            for row in strongest_halaqa_rows
        ],
        "لا توجد بيانات كافية لترتيب الحلقات.",
    )
    weakest_halaqas_table = _build_export_table(
        "أضعف الحلقات",
        ["الحلقة", "الفئة", "مؤشر القوة", "حالات المتابعة", "واجب معلق", "أحدث ملاحظة"],
        [
            [row["name"], row["category_name"], row["strength_score"], row["followup_students"], row["pending_homework_students"], row["latest_note"]]
            for row in weakest_halaqa_rows
        ],
        "لا توجد حلقات تحتاج ترتيب ضعف في هذا النطاق.",
    )
    student_summary_table = _build_export_table(
        "إشراف الطلاب بالتفصيل",
        ["الطالب", "الفئة", "الحلقة", "الحضور", "التسميع", "الخطة", "الواجب", "النقاط", "المتابعة"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["attendance_rate"], row["last_memorization_evaluation_label"], row["plan_target"], row["homework_status_label"], row["points_total"], row["followup_summary"]]
            for row in student_rows
        ],
        "لا توجد بيانات طلاب للتصدير ضمن هذا النطاق.",
    )
    points_leaderboard_table = _build_export_table(
        "ترتيب النقاط",
        ["الطالب", "الفئة", "الحلقة", "الرصيد", "تغير الفترة", "الحفظ"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["points_total"], row["points_in_range"], row["memorized_total"]]
            for row in points_leaderboard_rows
        ],
        "لا توجد حركات نقاط كافية للترتيب.",
    )
    at_risk_table = _build_export_table(
        "طلاب يحتاجون متابعة لصيقة",
        ["الطالب", "الفئة", "الحلقة", "الحضور", "الخطة", "الواجب", "الخلاصة"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["attendance_rate"], row["plan_target"], row["homework_status_label"], row["followup_summary"]]
            for row in at_risk_rows
        ],
        "لا توجد حالات عالية المخاطر ضمن هذا النطاق.",
    )
    plan_followup_table = _build_export_table(
        "الطلاب المتأخرون على الخطط",
        ["الطالب", "الفئة", "الحلقة", "الخطط النشطة", "الحضور", "الخطة الحالية", "أحدث تقييم"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["active_plans"], row["attendance_rate"], row["plan_target"], row["last_memorization_evaluation_label"]]
            for row in plan_followup_rows
        ],
        "لا توجد حالات تأخر ظاهرة على الخطط.",
    )
    active_plans_table = _build_export_table(
        "الطلاب المشمولون بخطط نشطة",
        ["الطالب", "الفئة", "الحلقة", "الخطة", "النافذة", "الحضور"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["plan_target"], row["plan_window"], row["attendance_rate"]]
            for row in students_with_active_plans_rows
        ],
        "لا توجد خطط نشطة ظاهرة ضمن هذا النطاق.",
    )
    weak_attendance_table = _build_export_table(
        "الطلاب ذوو الحضور الضعيف",
        ["الطالب", "الفئة", "الحلقة", "الحضور", "حاضر", "غائب", "معذور", "المرجع"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["attendance_rate"], row["attendance_present_total"], row["attendance_absent_total"], row["attendance_excused_total"], row["reference_attendance_label"]]
            for row in weak_attendance_rows
        ],
        "لا توجد حالات حضور ضعيف ضمن هذا النطاق.",
    )
    pending_homework_table = _build_export_table(
        "الواجبات بانتظار التقييم",
        ["الطالب", "الفئة", "الحلقة", "حالة الواجب", "ملخص الواجب", "الخطة"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["homework_status_label"], row["homework_meta_text"], row["plan_target"]]
            for row in pending_homework_rows
        ],
        "لا توجد واجبات معلقة بانتظار التقييم.",
    )
    homework_visible_table = _build_export_table(
        "ملخص واجبات الطلاب",
        ["الطالب", "الفئة", "الحلقة", "الحالة", "الملخص", "تفصيل"],
        [
            [row["name"], row["category"], row["halaqa_name"], row["homework_status_label"], row["homework_meta_text"], row["homework_detail_text"]]
            for row in homework_visible_rows
        ],
        "لا توجد واجبات نشطة أو معلقة للعرض.",
    )
    recent_points_table = _build_export_table(
        "أحدث حركات النقاط",
        ["الطالب", "الحلقة", "القيمة", "السبب", "التاريخ"],
        [
            [
                row.student.name,
                row.halaqa.name if row.halaqa_id else "بلا حلقة",
                row.value,
                row.reason or "بدون سبب نصي",
                timezone.localtime(row.date).strftime("%Y-%m-%d %H:%M"),
            ]
            for row in context["recent_point_rows"]
        ],
        "لا توجد حركات نقاط حديثة ضمن هذا النطاق.",
    )
    teacher_notes_table = _build_export_table(
        "ملاحظات المعلمين",
        ["المصدر", "المستفيد", "السياق", "الملاحظة", "الوقت"],
        [
            [
                row["source"],
                row["subject"],
                row["context"],
                row["note"],
                timezone.localtime(row["timestamp"]).strftime("%Y-%m-%d %H:%M"),
            ]
            for row in context["teacher_note_feed"]
        ],
        "لا توجد ملاحظات نصية مدخلة ضمن هذا النطاق.",
    )

    packages = {
        "executive_summary": {
            "title": "الملخص التنفيذي",
            "slug": "executive-summary",
            "subtitle": "ملخص إداري مبني على نفس بيانات المعلمين والفلاتر الحالية.",
            "summary_cards": [card(kpi["title"], kpi["value"], kpi["subtitle"]) for kpi in context["kpis"]],
            "summary_tables": [alerts_table],
            "detail_tables": [alerts_table, latest_registrations_table, category_summary_table],
        },
        "category_reports": {
            "title": "تقارير الفئات الرسمية",
            "slug": "category-reports",
            "subtitle": "ترتيبات وملخصات الفئات مع إبراز الحالات غير المحسومة إداريا.",
            "summary_cards": [
                card("الفئات الظاهرة", len(category_rows), "الفئات التي تقع ضمن هذا النطاق."),
                card("طلاب بلا فئة رسمية", context["category_foundation"]["missing_count"], "حالات تحتاج ربطا رسميا."),
                card("حلقات بلا فئة رسمية", context["category_foundation"]["halaqa_missing_count"], "توضح مواطن النقص في الهيكل الرسمي."),
                card("تنبيهات الوصول", context["category_foundation"]["access_count"], "طلاب دون ارتباط حساب ولي أمر."),
            ],
            "summary_tables": [category_attendance_table, category_memorization_table, category_points_table],
            "detail_tables": [category_attendance_table, category_memorization_table, category_points_table, category_summary_table, unresolved_table],
        },
        "halaqa_reports": {
            "title": "تقارير الحلقات",
            "slug": "halaqa-reports",
            "subtitle": "ملخص الحلقات وقوتها الإشرافية من الحضور والحفظ والنقاط.",
            "summary_cards": [
                card("الحلقات الظاهرة", len(halaqa_rows), "الحلقات التي يشملها النطاق الحالي."),
                card("الحلقات القوية", sum(1 for row in halaqa_rows if row["strength_score"] >= 80), "حلقات تقدم أداء إشرافيا مرتفعا."),
                card("الحلقات الضعيفة", sum(1 for row in halaqa_rows if row["strength_score"] < 60), "حلقات تحتاج إسنادا أو متابعة إضافية."),
                card("حلقات بلا فئة", context["category_foundation"]["halaqa_missing_count"], "تظهر كحالات إدارية مفتوحة."),
            ],
            "summary_tables": [strongest_halaqas_table, weakest_halaqas_table],
            "detail_tables": [halaqa_summary_table, strongest_halaqas_table, weakest_halaqas_table],
        },
        "student_reports": {
            "title": "تقارير الطلاب",
            "slug": "student-reports",
            "subtitle": "رؤية إشرافية موحدة للحضور والتسميع والخطط والواجب على مستوى الطالب.",
            "summary_cards": [
                card("الطلاب المرئيون", len(student_rows), "عدد الطلاب الذين تشملهم فلاتر الإدارة."),
                card("طلاب حضورهم ضعيف", len(weak_attendance_rows), "حالات قلت نسبة حضورها أو احتاجت تنبيها."),
                card("طلاب عالو المخاطر", len(at_risk_rows), "حالات تجمع أكثر من إشارة متابعة."),
                card("طلاب بخطط نشطة", len(students_with_active_plans_rows), "الطلاب المشمولون بخطط تربوية مفتوحة."),
            ],
            "summary_tables": [points_leaderboard_table, at_risk_table],
            "detail_tables": [student_summary_table, points_leaderboard_table, at_risk_table],
        },
        "plan_followup": {
            "title": "تقارير الخطط",
            "slug": "plan-followup",
            "subtitle": "تصدير مركز للخطط النشطة والحالات المتأخرة على التنفيذ.",
            "summary_cards": [
                card("إجمالي الخطط النشطة", context["plan_overview"]["active_total"], "خطط مفتوحة ضمن النطاق."),
                card("طلاب بخطط نشطة", context["plan_overview"]["students_covered"], "عدد الطلاب المشمولين بخطط جارية."),
                card("حالات تحتاج متابعة", context["plan_overview"]["needs_followup"], "حالات تأخرت عن المسار المتوقع."),
                card("بلا خطة نشطة", context["plan_overview"]["without_active_plan"], "طلاب مرتبطون بحلقة دون خطة جارية."),
            ],
            "summary_tables": [plan_followup_table],
            "detail_tables": [plan_followup_table, active_plans_table],
        },
        "attendance_risk": {
            "title": "تقارير الحضور",
            "slug": "attendance-risk",
            "subtitle": "متابعة إدارية للطلاب ذوي الحضور المنخفض والتغيب المتكرر.",
            "summary_cards": [
                card("حالات الحضور الضعيف", len(weak_attendance_rows), "تحت 75% أو حالات تنبيه إداري."),
                card("طلاب يحتاجون متابعة", len(at_risk_rows), "يظهرون مخاطر مرتبطة بالحضور والخطط والواجب."),
                card("عرض طلابي كامل", len(student_rows), "يمكن استخدامه كقاعدة للمتابعة الإدارية."),
                card("النطاق الزمني", context["date_window_label"], "مرجع احتساب سجلات الحضور."),
            ],
            "summary_tables": [weak_attendance_table],
            "detail_tables": [weak_attendance_table, student_summary_table],
        },
        "homework_pending": {
            "title": "تقارير الواجب",
            "slug": "homework-pending",
            "subtitle": "تصدير مخصص للواجبات المعلقة والحالات التي ما زالت تنتظر التقييم.",
            "summary_cards": [
                card("واجبات مسندة", context["homework_overview"]["assigned_in_range"], "الواجبات المسندة خلال النطاق."),
                card("واجبات مقيمة", context["homework_overview"]["evaluated_in_range"], "واجبات اكتمل تقييمها."),
                card("واجبات معلقة", context["homework_overview"]["pending_total"], "تنتظر تدخلا أو إغلاقا."),
                card("طلاب شملهم الواجب", context["homework_overview"]["students_covered"], "طلاب لهم حالة واجب مرئية."),
            ],
            "summary_tables": [pending_homework_table],
            "detail_tables": [pending_homework_table, homework_visible_table],
        },
        "points_reports": {
            "title": "تقارير النقاط",
            "slug": "points-reports",
            "subtitle": "ملخص لترتيب النقاط وحركاتها والملاحظات النصية المرتبطة بها.",
            "summary_cards": [
                card("صافي النقاط", context["points_overview"]["net_total"], "إجمالي الإضافات والخصومات في الفترة."),
                card("عدد الحركات", context["points_overview"]["transaction_total"], "جميع حركات النقاط المسجلة."),
                card("الطلاب المشمولون", context["points_overview"]["students_covered"], "الطلاب الذين شملتهم حركات النقاط."),
                card("إجمالي الخصومات", context["points_overview"]["deduction_total"], "خصومات سلوكية أو إدارية مرصودة."),
            ],
            "summary_tables": [points_leaderboard_table, recent_points_table],
            "detail_tables": [points_leaderboard_table, recent_points_table, teacher_notes_table],
        },
        "reports_bundle": {
            "title": "التقرير المجمع",
            "slug": "reports-bundle",
            "subtitle": "أهم ترتيبات الفئات والحلقات وحالات المخاطر في حزمة تقرير واحدة.",
            "summary_cards": [
                card("الفئات الظاهرة", len(category_rows), "يشمل الفئات الرسمية والحالات غير المحسومة."),
                card("أقوى الحلقات", len([row for row in strongest_halaqa_rows if row["strength_score"] >= 80]), "حلقات أظهرت قوة إشرافية مرتفعة."),
                card("طلاب عالو المخاطر", len(at_risk_rows), "حالات تحتاج تدخلا تربويا أو إداريا أسرع."),
                card("حالات غير محسومة", len(unresolved_rows), "طلاب أو حلقات تحتاج ربطا رسميا أو تنقيحا."),
            ],
            "summary_tables": [category_attendance_table, strongest_halaqas_table, at_risk_table],
            "detail_tables": [category_attendance_table, category_points_table, strongest_halaqas_table, weakest_halaqas_table, at_risk_table, pending_homework_table, unresolved_table, points_leaderboard_table],
        },
    }
    return packages[report_key]


def _build_admin_dashboard_csv_response(context, export_package, level):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"admin-dashboard-{export_package['slug']}-{level}-{timezone.localdate():%Y%m%d}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.write("\ufeff")
    writer = csv.writer(response)

    level_label = "ملخص" if level == "summary" else "تفصيلي"
    scope_rows = _build_export_scope_rows(context, export_package["title"], level_label)
    tables = export_package["summary_tables"] if level == "summary" else export_package["detail_tables"]

    writer.writerow([context["brand_title"], export_package["title"]])
    writer.writerow([export_package["subtitle"]])
    writer.writerow([])
    writer.writerow(["نطاق التصدير"])
    writer.writerow(["الحقل", "القيمة", "التفصيل"])
    for row in scope_rows:
        writer.writerow([row["label"], row["value"], row["detail"]])

    writer.writerow([])
    writer.writerow(["ملخص التقرير"])
    writer.writerow(["المؤشر", "القيمة", "التفصيل"])
    for row in export_package["summary_cards"]:
        writer.writerow([row["label"], row["value"], row["detail"]])

    for table in tables:
        writer.writerow([])
        writer.writerow([table["title"]])
        if not table["rows"]:
            writer.writerow([table["empty_message"]])
            continue
        writer.writerow(table["columns"])
        for row in table["rows"]:
            writer.writerow(row)
    return response


def _build_master_admin_dashboard_context(request):
    today = timezone.localdate()
    category_filter = request.GET.get("category", "")
    halaqa_filter = request.GET.get("halaqa", "")
    teacher_filter = request.GET.get("teacher", "")
    student_filter = request.GET.get("student", "")
    focus_student_filter = request.GET.get("focus_student", "")
    status_filter = request.GET.get("status", "all")
    date_range_filter = request.GET.get("range", "30d")
    start_date_raw = request.GET.get("start_date", "")
    end_date_raw = request.GET.get("end_date", "")
    start_date, end_date, date_range_filter = _resolve_date_window(
        date_range_filter,
        start_date_raw,
        end_date_raw,
    )
    reference_date = end_date
    if student_filter and not focus_student_filter:
        focus_student_filter = student_filter
    dashboard_base_url = reverse("halaqas:master_admin_dashboard")
    dashboard_filter_state = {
        "category": category_filter,
        "halaqa": halaqa_filter,
        "teacher": teacher_filter,
        "student": student_filter,
        "status": status_filter,
        "range": date_range_filter,
        "start_date": start_date.isoformat() if date_range_filter == "custom" else "",
        "end_date": end_date.isoformat() if date_range_filter == "custom" else "",
        "focus_student": focus_student_filter,
    }

    all_halaqas = Halaqa.objects.select_related("category").order_by("name")
    all_teachers = Teacher.objects.order_by("full_name")

    students_qs = Student.objects.select_related("parent", "category", "halaqa__category").all()
    if category_filter:
        if category_filter == UNRESOLVED_CATEGORY_FILTER:
            students_qs = students_qs.filter(category__isnull=True).filter(
                Q(halaqa__isnull=True) | Q(halaqa__category__isnull=True)
            )
        elif category_filter.isdigit():
            students_qs = students_qs.filter(
                Q(category_id=category_filter)
                | Q(category__isnull=True, halaqa__category_id=category_filter)
            )
    if halaqa_filter:
        students_qs = students_qs.filter(
            Q(halaqa_id=halaqa_filter)
            | Q(
                halaqa_memberships__halaqa_id=halaqa_filter,
                halaqa_memberships__is_active=True,
            )
        )
    if teacher_filter:
        students_qs = students_qs.filter(
            Q(halaqa__teachers__pk=teacher_filter)
            | Q(
                halaqa_memberships__halaqa__teachers__pk=teacher_filter,
                halaqa_memberships__is_active=True,
            )
        )
    student_option_qs = students_qs.distinct().order_by("name")
    if student_filter.isdigit():
        students_qs = student_option_qs.filter(pk=student_filter)
    else:
        students_qs = student_option_qs
    students = list(students_qs.distinct())
    student_ids = [student.id for student in students]

    membership_filters = Q(student_id__in=student_ids, is_active=True)
    if halaqa_filter:
        membership_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        membership_filters &= Q(halaqa__teachers__pk=teacher_filter)

    active_memberships = list(
        HalaqaMembership.objects.filter(membership_filters)
        .select_related("halaqa__category")
        .order_by("student_id", "-join_date")
    )
    membership_map = {}
    for membership in active_memberships:
        membership_map.setdefault(membership.student_id, membership)

    attendance_filters = Q(student_id__in=student_ids, session__date__range=(start_date, end_date))
    if halaqa_filter:
        attendance_filters &= Q(session__halaqa_id=halaqa_filter)
    if teacher_filter:
        attendance_filters &= Q(session__halaqa__teachers__pk=teacher_filter)
    attendance_rows = Attendance.objects.filter(attendance_filters).values("student_id").annotate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        excused=Count("id", filter=Q(status="excused")),
    )
    attendance_map = {row["student_id"]: row for row in attendance_rows}

    points_filters = Q(student_id__in=student_ids, date__date__range=(start_date, end_date))
    if halaqa_filter:
        points_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        points_filters &= Q(halaqa__teachers__pk=teacher_filter)
    points_rows = PointTransaction.objects.filter(points_filters).values("student_id").annotate(
        total=Coalesce(Sum("value"), 0)
    )
    points_map = {row["student_id"]: row["total"] for row in points_rows}

    memorization_rows = (
        MemorizationRecord.objects.filter(student_id__in=student_ids, date__range=(start_date, end_date))
        .values("student_id")
        .annotate(total=Coalesce(Sum(VERSE_COUNT_EXPR), 0))
    )
    memorization_map = {row["student_id"]: row["total"] for row in memorization_rows}

    plan_scope_filters = Q(student_id__in=student_ids)
    if halaqa_filter:
        plan_scope_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        plan_scope_filters &= Q(halaqa__teachers__pk=teacher_filter)

    active_plan_filters = plan_scope_filters & Q(is_completed=False)
    plan_rows = Plan.objects.filter(active_plan_filters).values("student_id").annotate(total=Count("id"))
    plan_map = {row["student_id"]: row["total"] for row in plan_rows}

    student_summaries = []
    for student in students:
        membership = membership_map.get(student.id)
        current_halaqa = membership.halaqa if membership else student.halaqa
        attendance = attendance_map.get(student.id, {})
        present = attendance.get("present", 0)
        absent = attendance.get("absent", 0)
        excused = attendance.get("excused", 0)
        attendance_rate = _resolve_attendance_rate(present, absent, excused)
        category_snapshot = _resolve_category_snapshot(student, membership)
        summary = {
            "id": student.id,
            "name": student.name,
            "grade": student.grade or "غير محدد",
            "category": category_snapshot["name"],
            "category_id": category_snapshot["id"],
            "category_code": category_snapshot["code"],
            "category_resolved": category_snapshot["resolved"],
            "category_hint": category_snapshot["hint"],
            "halaqa_name": current_halaqa.name if current_halaqa else "بلا حلقة",
            "halaqa_id": current_halaqa.id if current_halaqa else None,
            "parent_name": student.parent.first_name if student.parent else "بدون حساب",
            "has_parent_access": bool(student.parent_id),
            "created_at": student.created_at,
            "attendance_present": present,
            "attendance_absent": absent,
            "attendance_excused": excused,
            "attendance_rate": attendance_rate,
            "points_total": points_map.get(student.id, 0),
            "memorized_verses": memorization_map.get(student.id, 0),
            "active_plans": plan_map.get(student.id, 0),
        }
        summary["status"] = _resolve_student_status(summary)
        student_summaries.append(summary)

    if status_filter != "all":
        student_summaries = [
            summary for summary in student_summaries if summary["status"] == status_filter
        ]

    filtered_student_ids = [summary["id"] for summary in student_summaries]
    selected_teacher_ids = _get_selected_teacher_ids(teacher_filter)
    visible_plan_filters = Q(student_id__in=filtered_student_ids or student_ids)
    if halaqa_filter:
        visible_plan_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        visible_plan_filters &= Q(halaqa__teachers__pk=teacher_filter)

    halaqa_scope = Halaqa.objects.select_related("category").all()
    if category_filter:
        if category_filter == UNRESOLVED_CATEGORY_FILTER:
            halaqa_scope = halaqa_scope.filter(category__isnull=True)
        elif category_filter.isdigit():
            halaqa_scope = halaqa_scope.filter(category_id=category_filter)
    if halaqa_filter:
        halaqa_scope = halaqa_scope.filter(pk=halaqa_filter)
    if teacher_filter:
        halaqa_scope = halaqa_scope.filter(teachers__pk=teacher_filter)
    if student_filter.isdigit() and filtered_student_ids:
        halaqa_scope = halaqa_scope.filter(
            pk__in={summary["halaqa_id"] for summary in student_summaries if summary["halaqa_id"]}
        )
    halaqa_scope = halaqa_scope.distinct().annotate(
        active_student_count=Count("members__student", filter=Q(members__is_active=True), distinct=True),
        teacher_count=Count("teachers", distinct=True),
        total_points=Coalesce(Sum("pointtransaction__value"), 0),
    ).prefetch_related("teachers")

    attendance_today_filters = Q(session__date=today)
    if filtered_student_ids:
        attendance_today_filters &= Q(student_id__in=filtered_student_ids)
    elif student_ids:
        attendance_today_filters &= Q(student_id__in=student_ids)
    if halaqa_filter:
        attendance_today_filters &= Q(session__halaqa_id=halaqa_filter)
    if teacher_filter:
        attendance_today_filters &= Q(session__halaqa__teachers__pk=teacher_filter)

    attendance_today = Attendance.objects.filter(attendance_today_filters)
    today_present = attendance_today.filter(status="present").count()
    today_absent = attendance_today.filter(status="absent").count()

    total_students = len(student_summaries)
    total_teachers = (
        1
        if teacher_filter
        else all_teachers.filter(
            pk__in=selected_teacher_ids,
        ).count()
    )
    total_halaqas = halaqa_scope.count()
    total_categories = len(
        {
            summary["category_id"]
            for summary in student_summaries
            if summary["category_resolved"]
        }
    )
    active_students = sum(1 for summary in student_summaries if summary["halaqa_id"])
    average_attendance = (
        round(
            sum(summary["attendance_rate"] for summary in student_summaries) / total_students,
            1,
        )
        if total_students
        else 0
    )
    average_points = (
        round(
            sum(summary["points_total"] for summary in student_summaries) / total_students,
            1,
        )
        if total_students
        else 0
    )
    average_memorized = (
        round(
            sum(summary["memorized_verses"] for summary in student_summaries) / total_students,
            1,
        )
        if total_students
        else 0
    )
    performance_index = round(
        (average_attendance * 0.55)
        + (min(average_points, 100) * 0.25)
        + (min(average_memorized * 2, 100) * 0.20),
        1,
    )

    kpis = [
        {
            "title": "إجمالي الطلاب",
            "value": total_students,
            "subtitle": "ضمن نطاق الفلاتر الحالي",
            "icon": "fa-user-graduate",
            "tone": "primary",
        },
        {
            "title": "إجمالي المعلمين",
            "value": total_teachers,
            "subtitle": "معلمون مرتبطون بالحلقات المختارة",
            "icon": "fa-chalkboard-user",
            "tone": "secondary",
        },
        {
            "title": "إجمالي الحلقات",
            "value": total_halaqas,
            "subtitle": "حلقات ظاهرة في لوحة الإدارة",
            "icon": "fa-mosque",
            "tone": "accent",
        },
        {
            "title": "إجمالي التصنيفات",
            "value": total_categories,
            "subtitle": "فئات رسمية ظاهرة في نطاق التقرير الحالي",
            "icon": "fa-layer-group",
            "tone": "info",
        },
        {
            "title": "الطلاب النشطون",
            "value": active_students,
            "subtitle": "لديهم حلقة مفعلة",
            "icon": "fa-user-check",
            "tone": "success",
        },
        {
            "title": "حضور اليوم",
            "value": today_present,
            "subtitle": "حضور مسجل في جلسات اليوم",
            "icon": "fa-calendar-check",
            "tone": "success",
        },
        {
            "title": "غيابات اليوم",
            "value": today_absent,
            "subtitle": "غياب يحتاج متابعة",
            "icon": "fa-user-xmark",
            "tone": "danger",
        },
        {
            "title": "مؤشر الأداء العام",
            "value": f"{performance_index}%",
            "subtitle": "مزيج من الحضور والنقاط والحفظ",
            "icon": "fa-chart-line",
            "tone": "warning",
        },
    ]

    category_counter = Counter(summary["category"] for summary in student_summaries)
    students_by_category_chart = {
        "labels": list(category_counter.keys()) or ["لا توجد بيانات"],
        "values": list(category_counter.values()) or [0],
        "is_demo": False,
    }

    halaqa_counter = Counter(summary["halaqa_name"] for summary in student_summaries if summary["halaqa_name"])
    students_by_halaqa_chart = {
        "labels": list(halaqa_counter.keys()) or ["لا توجد بيانات"],
        "values": list(halaqa_counter.values()) or [0],
        "is_demo": False,
    }

    attendance_trend_rows = list(
        Attendance.objects.filter(attendance_filters)
        .values("session__date")
        .annotate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
        )
        .order_by("session__date")
    )
    if attendance_trend_rows:
        attendance_trends_chart = {
            "labels": [_format_day_label(row["session__date"]) for row in attendance_trend_rows],
            "present": [row["present"] for row in attendance_trend_rows],
            "absent": [row["absent"] for row in attendance_trend_rows],
            "is_demo": False,
        }
    else:
        attendance_trends_chart = {
            "labels": ["الأسبوع 1", "الأسبوع 2", "الأسبوع 3", "الأسبوع 4"],
            "present": [26, 31, 29, 34],
            "absent": [4, 3, 5, 2],
            "is_demo": True,
        }

    performance_trend_rows = list(
        MemorizationRecord.objects.filter(
            student_id__in=filtered_student_ids or student_ids,
            date__range=(start_date, end_date),
        )
        .values("date")
        .annotate(total=Coalesce(Sum(VERSE_COUNT_EXPR), 0))
        .order_by("date")
    )
    if performance_trend_rows:
        performance_trends_chart = {
            "labels": [_format_day_label(row["date"]) for row in performance_trend_rows],
            "values": [row["total"] for row in performance_trend_rows],
            "is_demo": False,
        }
    else:
        performance_trends_chart = _build_fallback_series(
            ["الأسبوع 1", "الأسبوع 2", "الأسبوع 3", "الأسبوع 4"],
            [18, 24, 21, 29],
        )

    teacher_distribution_rows = list(
        Teacher.objects.filter(pk__in=selected_teacher_ids)
        .annotate(
            student_total=Count(
                "halaqas__members__student",
                filter=Q(halaqas__members__is_active=True),
                distinct=True,
            ),
            halaqa_total=Count("halaqas", distinct=True),
        )
        .order_by("-student_total", "full_name")[:6]
    )
    teacher_distribution_chart = {
        "labels": [teacher.full_name for teacher in teacher_distribution_rows] or ["لا توجد بيانات"],
        "values": [teacher.student_total for teacher in teacher_distribution_rows] or [0],
        "meta": [teacher.halaqa_total for teacher in teacher_distribution_rows] or [0],
        "is_demo": False,
    }

    top_halaqas_rows = list(halaqa_scope.order_by("-total_points", "-active_student_count", "name")[:6])
    top_halaqas_chart = {
        "labels": [halaqa.name for halaqa in top_halaqas_rows] or ["لا توجد بيانات"],
        "values": [halaqa.total_points for halaqa in top_halaqas_rows] or [0],
        "students": [halaqa.active_student_count for halaqa in top_halaqas_rows] or [0],
        "is_demo": False,
    }

    weak_attendance_students = sorted(
        [
            summary
            for summary in student_summaries
            if summary["attendance_rate"] < 75 or summary["status"] == "attention"
        ],
        key=lambda item: (item["attendance_rate"], item["points_total"]),
    )
    weak_attendance_chart_rows = weak_attendance_students[:6]
    students_attention_chart = {
        "labels": [student["name"] for student in weak_attendance_chart_rows] or ["لا توجد حالات حرجة"],
        "values": [student["attendance_rate"] for student in weak_attendance_chart_rows] or [0],
        "is_demo": False,
    }

    latest_registrations = sorted(
        student_summaries,
        key=lambda item: item["created_at"],
        reverse=True,
    )[:6]
    top_students = sorted(
        student_summaries,
        key=lambda item: (item["points_total"], item["memorized_verses"]),
        reverse=True,
    )[:6]
    students_with_active_plans = sorted(
        [summary for summary in student_summaries if summary["active_plans"]],
        key=lambda item: (item["active_plans"], item["attendance_rate"], item["points_total"]),
        reverse=True,
    )
    students_without_active_plans_count = sum(
        1 for summary in student_summaries if summary["halaqa_id"] and not summary["active_plans"]
    )
    plan_followup_students = sorted(
        [
            summary
            for summary in students_with_active_plans
            if summary["status"] != "active" or summary["attendance_rate"] < 75
        ],
        key=lambda item: (item["attendance_rate"], -item["active_plans"], item["name"]),
    )

    recent_plan_rows = list(
        Plan.objects.filter(visible_plan_filters, is_completed=False)
        .select_related("student", "halaqa")
        .order_by("-start_date", "-id")[:6]
    )
    completed_plan_count = Plan.objects.filter(
        visible_plan_filters,
        is_completed=True,
        end_date__range=(start_date, end_date),
    ).count()
    plan_overview = {
        "active_total": sum(summary["active_plans"] for summary in student_summaries),
        "students_covered": len(students_with_active_plans),
        "needs_followup": len(plan_followup_students),
        "completed_in_range": completed_plan_count,
        "without_active_plan": students_without_active_plans_count,
    }

    homework_scope_filters = Q(student_id__in=filtered_student_ids or student_ids)
    if halaqa_filter:
        homework_scope_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        homework_scope_filters &= Q(halaqa__teachers__pk=teacher_filter)

    recent_homework_rows = list(
        Homework.objects.filter(homework_scope_filters, assigned_date__lte=end_date)
        .select_related("student", "halaqa")
        .order_by("-assigned_date", "-id")[:6]
    )
    pending_homework_rows = list(
        Homework.objects.filter(homework_scope_filters, assigned_date__lte=end_date)
        .filter(Q(evaluation_date__isnull=True) | Q(evaluation_date__gt=end_date))
        .select_related("student", "halaqa")
        .order_by("-assigned_date", "-id")[:6]
    )
    homework_overview = {
        "assigned_in_range": Homework.objects.filter(
            homework_scope_filters,
            assigned_date__range=(start_date, end_date),
        ).count(),
        "evaluated_in_range": Homework.objects.filter(
            homework_scope_filters,
            evaluation_date__range=(start_date, end_date),
        ).count(),
        "pending_total": Homework.objects.filter(
            homework_scope_filters,
            assigned_date__lte=end_date,
        )
        .filter(Q(evaluation_date__isnull=True) | Q(evaluation_date__gt=end_date))
        .count(),
        "students_covered": Homework.objects.filter(homework_scope_filters)
        .values("student_id")
        .distinct()
        .count(),
    }

    visible_student_ids = filtered_student_ids
    visible_halaqa_rows = list(halaqa_scope.order_by("name"))
    scope_halaqa_ids = [halaqa.id for halaqa in visible_halaqa_rows]
    visible_attendance_range_filters = Q(
        student_id__in=visible_student_ids,
        session__date__range=(start_date, end_date),
    )
    visible_points_range_filters = Q(
        student_id__in=visible_student_ids,
        date__date__range=(start_date, end_date),
    )
    visible_plan_note_filters = Q(student_id__in=visible_student_ids)
    visible_homework_note_filters = Q(student_id__in=visible_student_ids)
    if halaqa_filter:
        visible_attendance_range_filters &= Q(session__halaqa_id=halaqa_filter)
        visible_points_range_filters &= Q(halaqa_id=halaqa_filter)
        visible_plan_note_filters &= Q(halaqa_id=halaqa_filter)
        visible_homework_note_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        visible_attendance_range_filters &= Q(session__halaqa__teachers__pk=teacher_filter)
        visible_points_range_filters &= Q(halaqa__teachers__pk=teacher_filter)
        visible_plan_note_filters &= Q(halaqa__teachers__pk=teacher_filter)
        visible_homework_note_filters &= Q(halaqa__teachers__pk=teacher_filter)

    cumulative_attendance_filters = Q(
        student_id__in=visible_student_ids,
        session__date__lte=reference_date,
    )
    if halaqa_filter:
        cumulative_attendance_filters &= Q(session__halaqa_id=halaqa_filter)
    if teacher_filter:
        cumulative_attendance_filters &= Q(session__halaqa__teachers__pk=teacher_filter)
    cumulative_attendance_rows = Attendance.objects.filter(cumulative_attendance_filters).values("student_id").annotate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        excused=Count("id", filter=Q(status="excused")),
    )
    cumulative_attendance_map = {
        row["student_id"]: {
            "present": row["present"],
            "absent": row["absent"],
            "excused": row["excused"],
        }
        for row in cumulative_attendance_rows
    }
    reference_attendance_map = {}
    for attendance in Attendance.objects.filter(
        cumulative_attendance_filters & Q(session__date=reference_date)
    ).select_related("session__halaqa"):
        reference_attendance_map[attendance.student_id] = attendance

    cumulative_points_filters = Q(
        student_id__in=visible_student_ids,
        date__date__lte=reference_date,
    )
    if halaqa_filter:
        cumulative_points_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        cumulative_points_filters &= Q(halaqa__teachers__pk=teacher_filter)
    cumulative_points_rows = PointTransaction.objects.filter(cumulative_points_filters).values("student_id").annotate(
        total=Coalesce(Sum("value"), 0)
    )
    cumulative_points_map = {
        row["student_id"]: row["total"]
        for row in cumulative_points_rows
    }
    recent_point_by_student = {}
    for transaction in PointTransaction.objects.filter(cumulative_points_filters).select_related(
        "student",
        "halaqa",
    ).order_by("student_id", "-date", "-id"):
        recent_point_by_student.setdefault(transaction.student_id, transaction)

    cumulative_memorization_rows = MemorizationRecord.objects.filter(
        student_id__in=visible_student_ids,
        date__lte=reference_date,
    ).values("student_id").annotate(
        total=Coalesce(Sum(VERSE_COUNT_EXPR), 0),
        records_count=Count("id"),
    )
    cumulative_memorization_map = {
        row["student_id"]: row["total"]
        for row in cumulative_memorization_rows
    }
    cumulative_memorization_count_map = {
        row["student_id"]: row["records_count"]
        for row in cumulative_memorization_rows
    }
    last_memorization_map = {}
    for record in MemorizationRecord.objects.filter(
        student_id__in=visible_student_ids,
        date__lte=reference_date,
    ).select_related("student").order_by("student_id", "-date", "-id"):
        last_memorization_map.setdefault(record.student_id, record)

    current_plan_filters = Q(
        student_id__in=visible_student_ids,
        is_completed=False,
        start_date__lte=reference_date,
        end_date__gte=reference_date,
    )
    if halaqa_filter:
        current_plan_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        current_plan_filters &= Q(halaqa__teachers__pk=teacher_filter)

    current_plan_map = {}
    for plan in Plan.objects.filter(current_plan_filters).select_related("halaqa").order_by(
        "student_id",
        "-start_date",
        "-id",
    ):
        current_plan_map.setdefault(plan.student_id, plan)

    current_homework_filters = Q(
        student_id__in=visible_student_ids,
        assigned_date__lte=reference_date,
    )
    if halaqa_filter:
        current_homework_filters &= Q(halaqa_id=halaqa_filter)
    if teacher_filter:
        current_homework_filters &= Q(halaqa__teachers__pk=teacher_filter)

    current_homework_map = {}
    for homework in Homework.objects.filter(current_homework_filters).select_related(
        "halaqa"
    ).order_by("student_id", "-assigned_date", "-id"):
        current_homework_map.setdefault(
            homework.student_id,
            _build_homework_snapshot(homework, reference_date),
        )

    latest_session_map = {}
    latest_session_note_map = {}
    if scope_halaqa_ids:
        for session in Session.objects.filter(
            halaqa_id__in=scope_halaqa_ids,
            date__lte=reference_date,
        ).select_related("halaqa").order_by("halaqa_id", "-date", "-id"):
            latest_session_map.setdefault(session.halaqa_id, session)
            if session.notes:
                latest_session_note_map.setdefault(session.halaqa_id, session)

    halaqa_points_total_map = {}
    halaqa_points_range_map = {}
    if scope_halaqa_ids:
        halaqa_point_filters = Q(halaqa_id__in=scope_halaqa_ids)
        if teacher_filter:
            halaqa_point_filters &= Q(halaqa__teachers__pk=teacher_filter)

        for row in PointTransaction.objects.filter(
            halaqa_point_filters,
            date__date__lte=reference_date,
        ).values("halaqa_id").annotate(total=Coalesce(Sum("value"), 0)):
            halaqa_points_total_map[row["halaqa_id"]] = row["total"]

        for row in PointTransaction.objects.filter(
            halaqa_point_filters,
            date__date__range=(start_date, end_date),
        ).values("halaqa_id").annotate(total=Coalesce(Sum("value"), 0)):
            halaqa_points_range_map[row["halaqa_id"]] = row["total"]

    halaqa_attendance_trend_map = {}
    for row in Attendance.objects.filter(visible_attendance_range_filters).values(
        "session__halaqa_id",
        "session__date",
    ).annotate(
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        excused=Count("id", filter=Q(status="excused")),
    ).order_by("session__halaqa_id", "session__date"):
        halaqa_attendance_trend_map.setdefault(row["session__halaqa_id"], []).append(
            {
                "date": row["session__date"],
                "rate": _resolve_attendance_rate(
                    row["present"],
                    row["absent"],
                    row["excused"],
                ),
            }
        )

    student_supervision_rows = []
    for summary in student_summaries:
        student_id = summary["id"]
        current_plan = current_plan_map.get(student_id)
        current_homework = current_homework_map.get(student_id)
        latest_memorization = last_memorization_map.get(student_id)
        latest_point = recent_point_by_student.get(student_id)
        latest_session_note = latest_session_note_map.get(summary["halaqa_id"])
        cumulative_attendance = cumulative_attendance_map.get(
            student_id,
            {"present": 0, "absent": 0, "excused": 0},
        )
        cumulative_attendance_rate = _resolve_attendance_rate(
            cumulative_attendance["present"],
            cumulative_attendance["absent"],
            cumulative_attendance["excused"],
        )
        reference_attendance = reference_attendance_map.get(student_id)
        notes = _collect_notes(
            (
                f"ملاحظة حضور {reference_date.isoformat()}: {reference_attendance.notes}"
                if reference_attendance and reference_attendance.notes
                else ""
            ),
            (
                f"الخطة: {current_plan.notes}"
                if current_plan and current_plan.notes
                else ""
            ),
            (
                f"إسناد الواجب: {current_homework['assignment_notes']}"
                if current_homework and current_homework.get("assignment_notes")
                else ""
            ),
            (
                f"تقييم الواجب: {current_homework['evaluation_notes']}"
                if current_homework and current_homework.get("evaluation_notes")
                else ""
            ),
            (
                f"سبب النقاط: {latest_point.reason}"
                if latest_point and latest_point.reason
                else ""
            ),
            (
                f"ملاحظة الجلسة: {latest_session_note.notes}"
                if latest_session_note and latest_session_note.notes
                else ""
            ),
        )
        student_supervision_rows.append(
            {
                "id": student_id,
                "name": summary["name"],
                "grade": summary["grade"],
                "category": summary["category"],
                "category_id": summary["category_id"],
                "category_code": summary["category_code"],
                "category_resolved": summary["category_resolved"],
                "category_hint": summary["category_hint"],
                "halaqa_id": summary["halaqa_id"],
                "halaqa_name": summary["halaqa_name"],
                "status": summary["status"],
                "status_label": {
                    "active": "نشط",
                    "attention": "يحتاج متابعة",
                    "unassigned": "غير مسند",
                }[summary["status"]],
                "status_tone": _status_tone(
                    summary["status"],
                    {
                        "active": "success",
                        "attention": "warning",
                        "unassigned": "danger",
                    },
                ),
                "attendance_present_total": cumulative_attendance["present"],
                "attendance_absent_total": cumulative_attendance["absent"],
                "attendance_excused_total": cumulative_attendance["excused"],
                "attendance_rate": cumulative_attendance_rate,
                "attendance_window_rate": summary["attendance_rate"],
                "reference_attendance_status": reference_attendance.status if reference_attendance else "",
                "reference_attendance_label": (
                    reference_attendance.get_status_display()
                    if reference_attendance
                    else "غير مسجل"
                ),
                "reference_attendance_notes": reference_attendance.notes if reference_attendance else "",
                "reference_attendance_tone": _status_tone(
                    reference_attendance.status if reference_attendance else "",
                    {
                        "present": "success",
                        "absent": "danger",
                        "excused": "warning",
                    },
                ),
                "points_total": cumulative_points_map.get(student_id, 0),
                "points_in_range": summary["points_total"],
                "memorized_total": cumulative_memorization_map.get(student_id, 0),
                "memorized_in_range": summary["memorized_verses"],
                "memorization_records_total": cumulative_memorization_count_map.get(student_id, 0),
                "last_memorization": latest_memorization,
                "last_memorization_text": (
                    f"{latest_memorization.recitation_title} {latest_memorization.recitation_range}".strip()
                    if latest_memorization
                    else "لا يوجد تسميع مسجل"
                ),
                "last_memorization_date": latest_memorization.date if latest_memorization else None,
                "last_memorization_evaluation_label": (
                    latest_memorization.get_evaluation_display()
                    if latest_memorization and latest_memorization.evaluation
                    else "غير مقيم"
                ),
                "last_memorization_tone": _status_tone(
                    latest_memorization.evaluation if latest_memorization else "",
                    {
                        "excellent": "success",
                        "very_good": "success",
                        "good": "info",
                        "needs_followup": "warning",
                    },
                ),
                "plan": current_plan,
                "active_plans": summary["active_plans"],
                "plan_target": current_plan.target if current_plan else "لا توجد خطة نشطة",
                "plan_window": (
                    f"{current_plan.start_date:%Y-%m-%d} - {current_plan.end_date:%Y-%m-%d}"
                    if current_plan
                    else ""
                ),
                "plan_notes": current_plan.notes if current_plan else "",
                "homework": current_homework,
                "homework_status": current_homework["status"] if current_homework else "none",
                "homework_status_label": current_homework["status_label"] if current_homework else "لا يوجد واجب حالي",
                "homework_meta_text": current_homework["meta_text"] if current_homework else "لا يوجد واجب حالي",
                "homework_detail_text": current_homework["detail_text"] if current_homework else "",
                "homework_status_tone": _status_tone(
                    current_homework["status"] if current_homework else "",
                    {
                        "evaluated": "success",
                        "pending": "warning",
                        "assigned": "info",
                    },
                ),
                "notes": notes,
                "notes_excerpt": notes[0] if notes else "لا توجد ملاحظات معلم مسجلة",
                "focus_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="studentsPanel",
                ),
                "halaqa_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": summary["halaqa_id"], "student": student_id, "focus_student": student_id},
                    fragment="halaqasPanel",
                ) if summary["halaqa_id"] else "",
                "category_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={
                        "category": summary["category_id"],
                        "halaqa": None,
                        "student": student_id,
                        "focus_student": student_id,
                    },
                    fragment="reportsPanel",
                ),
                "attendance_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="attendancePanel",
                ),
                "plans_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="plansPanel",
                ),
                "homework_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="homeworkPanel",
                ),
                "points_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="reportsPanel",
                ),
                "reports_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"student": student_id, "focus_student": student_id},
                    fragment="reportsPanel",
                ),
            }
        )

    for row in student_supervision_rows:
        followup_reasons = []
        if not row["halaqa_id"]:
            followup_reasons.append("غير مسند إلى حلقة")
        if not row["category_resolved"]:
            if row["category_hint"]:
                followup_reasons.append(f"تصنيف رسمي غير مكتمل، والقرينة الأقرب: {row['category_hint']}")
            else:
                followup_reasons.append("تصنيف رسمي غير مكتمل")
        if row["attendance_rate"] < 75:
            followup_reasons.append("حضور منخفض")
        if not row["plan"] and row["halaqa_id"]:
            followup_reasons.append("لا توجد خطة نشطة")
        if row["homework_status"] in {"assigned", "pending"}:
            followup_reasons.append("واجب بانتظار المتابعة أو التقييم")
        if row["last_memorization"] and row["last_memorization"].evaluation == "needs_followup":
            followup_reasons.append("آخر تسميع يحتاج متابعة")
        row["followup_reasons"] = followup_reasons
        row["followup_summary"] = " | ".join(followup_reasons) if followup_reasons else "مستقر"
        row["at_risk"] = bool(followup_reasons)

    student_supervision_rows = sorted(
        student_supervision_rows,
        key=lambda item: (
            0 if item["at_risk"] else 1,
            item["attendance_rate"],
            -item["points_total"],
            item["name"],
        ),
    )

    focused_student = None
    if focus_student_filter.isdigit():
        focused_student = next(
            (item for item in student_supervision_rows if item["id"] == int(focus_student_filter)),
            None,
        )
    if focused_student is None and student_supervision_rows:
        focused_student = student_supervision_rows[0]

    halaqa_student_map = {}
    for item in student_supervision_rows:
        if item["halaqa_id"]:
            halaqa_student_map.setdefault(item["halaqa_id"], []).append(item)

    halaqa_supervision_rows = []
    for halaqa in visible_halaqa_rows:
        halaqa_students = halaqa_student_map.get(halaqa.id, [])
        attendance_present_total = sum(item["attendance_present_total"] for item in halaqa_students)
        attendance_absent_total = sum(item["attendance_absent_total"] for item in halaqa_students)
        attendance_excused_total = sum(item["attendance_excused_total"] for item in halaqa_students)
        attendance_rate = _resolve_attendance_rate(
            attendance_present_total,
            attendance_absent_total,
            attendance_excused_total,
        )
        attendance_trend_label, attendance_trend_tone = _describe_attendance_trend(
            halaqa_attendance_trend_map.get(halaqa.id, [])
        )
        active_plan_students = sum(1 for item in halaqa_students if item["plan"])
        pending_homework_students = sum(
            1 for item in halaqa_students if item["homework_status"] in {"assigned", "pending"}
        )
        evaluated_homework_students = sum(
            1 for item in halaqa_students if item["homework_status"] == "evaluated"
        )
        followup_students = sum(
            1
            for item in halaqa_students
            if item["status"] != "active"
            or (
                item["last_memorization"]
                and item["last_memorization"].evaluation == "needs_followup"
            )
        )
        signal_label, signal_tone = _resolve_halaqa_signal(
            attendance_rate=attendance_rate,
            pending_homework=pending_homework_students,
            followup_students=followup_students,
            points_delta=halaqa_points_range_map.get(halaqa.id, 0),
        )
        latest_session = latest_session_map.get(halaqa.id)
        latest_note = ""
        if halaqa.id in latest_session_note_map:
            latest_note = latest_session_note_map[halaqa.id].notes
        elif halaqa_students:
            latest_note = halaqa_students[0]["notes_excerpt"]

        halaqa_supervision_rows.append(
            {
                "id": halaqa.id,
                "name": halaqa.name,
                "category_id": str(halaqa.category_id) if halaqa.category_id else UNRESOLVED_CATEGORY_FILTER,
                "category_code": halaqa.category.code if halaqa.category_id else UNRESOLVED_CATEGORY_FILTER,
                "category_name": halaqa.category.name if halaqa.category_id else UNRESOLVED_CATEGORY_LABEL,
                "category_resolved": bool(halaqa.category_id),
                "teacher_names": "، ".join(
                    teacher.full_name for teacher in halaqa.teachers.all()
                ) or "بدون معلم",
                "student_count": len(halaqa_students),
                "attendance_rate": attendance_rate,
                "attendance_present_total": attendance_present_total,
                "attendance_absent_total": attendance_absent_total,
                "attendance_excused_total": attendance_excused_total,
                "attendance_trend_label": attendance_trend_label,
                "attendance_trend_tone": attendance_trend_tone,
                "memorized_total": sum(item["memorized_total"] for item in halaqa_students),
                "memorized_in_range": sum(item["memorized_in_range"] for item in halaqa_students),
                "active_plan_students": active_plan_students,
                "pending_homework_students": pending_homework_students,
                "evaluated_homework_students": evaluated_homework_students,
                "followup_students": followup_students,
                "points_total": halaqa_points_total_map.get(halaqa.id, 0),
                "points_in_range": halaqa_points_range_map.get(halaqa.id, 0),
                "signal_label": signal_label,
                "signal_tone": signal_tone,
                "latest_session_label": (
                    latest_session.date.strftime("%Y-%m-%d")
                    if latest_session
                    else "لا توجد جلسة مسجلة"
                ),
                "latest_note": latest_note or "لا توجد ملاحظات معلمين مسجلة",
                "students_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="studentsPanel",
                ),
                "plans_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="plansPanel",
                ),
                "attendance_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="attendancePanel",
                ),
                "homework_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="homeworkPanel",
                ),
                "points_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="reportsPanel",
                ),
                "reports_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={"halaqa": halaqa.id, "student": None, "focus_student": None},
                    fragment="reportsPanel",
                ),
                "category_url": _dashboard_url(
                    dashboard_base_url,
                    dashboard_filter_state,
                    overrides={
                        "category": str(halaqa.category_id) if halaqa.category_id else UNRESOLVED_CATEGORY_FILTER,
                        "halaqa": halaqa.id,
                        "student": None,
                        "focus_student": None,
                    },
                    fragment="reportsPanel",
                ),
            }
        )

    for row in halaqa_supervision_rows:
        strength_score = _resolve_halaqa_strength_score(row)
        row["strength_score"] = strength_score
        row["strength_tone"] = _resolve_halaqa_strength_tone(strength_score)

    halaqa_supervision_rows = sorted(
        halaqa_supervision_rows,
        key=lambda item: (
            -item["strength_score"],
            -item["student_count"],
            item["name"],
        ),
    )

    strongest_halaqas = halaqa_supervision_rows[:8]
    weakest_halaqas = sorted(
        halaqa_supervision_rows,
        key=lambda item: (item["strength_score"], -item["followup_students"], item["name"]),
    )[:8]
    top_halaqas_chart = {
        "labels": [halaqa["name"] for halaqa in strongest_halaqas] or ["لا توجد بيانات"],
        "values": [halaqa["strength_score"] for halaqa in strongest_halaqas] or [0],
        "students": [halaqa["student_count"] for halaqa in strongest_halaqas] or [0],
        "is_demo": False,
    }

    category_map = {}
    for halaqa in halaqa_supervision_rows:
        category_row = category_map.setdefault(
            halaqa["category_id"],
            {
                "id": halaqa["category_id"],
                "code": halaqa["category_code"],
                "name": halaqa["category_name"],
                "resolved": halaqa["category_resolved"],
                "student_count": 0,
                "halaqa_count": 0,
                "attendance_present_total": 0,
                "attendance_absent_total": 0,
                "attendance_excused_total": 0,
                "memorized_total": 0,
                "memorized_in_range": 0,
                "points_total": 0,
                "points_in_range": 0,
                "active_plan_students": 0,
                "students_without_plan": 0,
                "pending_homework_students": 0,
                "evaluated_homework_students": 0,
                "followup_students": 0,
                "unresolved_students": 0,
                "unresolved_halaqas": 0,
                "hint_samples": set(),
            },
        )
        category_row["halaqa_count"] += 1
        if not halaqa["category_resolved"]:
            category_row["unresolved_halaqas"] += 1

    for student in student_supervision_rows:
        category_row = category_map.setdefault(
            student["category_id"],
            {
                "id": student["category_id"],
                "code": student["category_code"],
                "name": student["category"],
                "resolved": student["category_resolved"],
                "student_count": 0,
                "halaqa_count": 0,
                "attendance_present_total": 0,
                "attendance_absent_total": 0,
                "attendance_excused_total": 0,
                "memorized_total": 0,
                "memorized_in_range": 0,
                "points_total": 0,
                "points_in_range": 0,
                "active_plan_students": 0,
                "students_without_plan": 0,
                "pending_homework_students": 0,
                "evaluated_homework_students": 0,
                "followup_students": 0,
                "unresolved_students": 0,
                "unresolved_halaqas": 0,
                "hint_samples": set(),
            },
        )
        category_row["student_count"] += 1
        category_row["attendance_present_total"] += student["attendance_present_total"]
        category_row["attendance_absent_total"] += student["attendance_absent_total"]
        category_row["attendance_excused_total"] += student["attendance_excused_total"]
        category_row["memorized_total"] += student["memorized_total"]
        category_row["memorized_in_range"] += student["memorized_in_range"]
        category_row["points_total"] += student["points_total"]
        category_row["points_in_range"] += student["points_in_range"]
        category_row["followup_students"] += 1 if student["at_risk"] else 0
        if student["plan"]:
            category_row["active_plan_students"] += 1
        elif student["halaqa_id"]:
            category_row["students_without_plan"] += 1
        if student["homework_status"] in {"assigned", "pending"}:
            category_row["pending_homework_students"] += 1
        if student["homework_status"] == "evaluated":
            category_row["evaluated_homework_students"] += 1
        if not student["category_resolved"]:
            category_row["unresolved_students"] += 1
            if student["category_hint"]:
                category_row["hint_samples"].add(student["category_hint"])

    category_supervision_rows = []
    for category_row in category_map.values():
        attendance_rate = _resolve_attendance_rate(
            category_row["attendance_present_total"],
            category_row["attendance_absent_total"],
            category_row["attendance_excused_total"],
        )
        hint_samples = sorted(category_row["hint_samples"])
        category_row["attendance_rate"] = attendance_rate
        category_row["memorization_per_student"] = round(
            category_row["memorized_in_range"] / category_row["student_count"],
            1,
        ) if category_row["student_count"] else 0
        category_row["points_per_student"] = round(
            category_row["points_in_range"] / category_row["student_count"],
            1,
        ) if category_row["student_count"] else 0
        category_row["hint_summary"] = " | ".join(hint_samples[:3]) if hint_samples else ""
        category_row["filter_url"] = _dashboard_url(
            dashboard_base_url,
            dashboard_filter_state,
            overrides={
                "category": category_row["id"],
                "halaqa": None,
                "student": None,
                "focus_student": None,
            },
            fragment="reportsPanel",
        )
        category_supervision_rows.append(category_row)

    category_supervision_rows = sorted(
        category_supervision_rows,
        key=lambda item: (-item["student_count"], item["name"]),
    )
    category_attendance_ranking = sorted(
        category_supervision_rows,
        key=lambda item: (-item["attendance_rate"], -item["student_count"], item["name"]),
    )
    category_memorization_ranking = sorted(
        category_supervision_rows,
        key=lambda item: (-item["memorized_in_range"], -item["memorized_total"], item["name"]),
    )
    category_points_ranking = sorted(
        category_supervision_rows,
        key=lambda item: (-item["points_in_range"], -item["points_total"], item["name"]),
    )
    unresolved_category_rows = [
        {
            "type": "طالب",
            "name": student["name"],
            "scope": student["halaqa_name"],
            "detail": student["followup_summary"],
            "hint": student["category_hint"] or "لا توجد قرينة صفية واضحة",
            "url": student["focus_url"],
        }
        for student in student_supervision_rows
        if not student["category_resolved"]
    ]
    unresolved_category_rows.extend(
        {
            "type": "حلقة",
            "name": halaqa["name"],
            "scope": halaqa["teacher_names"],
            "detail": "لم تربط بعد بفئة رسمية",
            "hint": "راجع تصنيف الحلقة أو الطلاب المرتبطين بها",
            "url": halaqa["students_url"],
        }
        for halaqa in halaqa_supervision_rows
        if not halaqa["category_resolved"]
    )
    unresolved_category_rows = unresolved_category_rows[:10]

    weak_attendance_students = []
    for student in student_supervision_rows:
        if student["attendance_rate"] < 75 or student["status"] == "attention":
            weak_item = dict(student)
            weak_item["attendance_absent"] = student["attendance_absent_total"]
            weak_attendance_students.append(weak_item)
    weak_attendance_students = sorted(
        weak_attendance_students,
        key=lambda item: (item["attendance_rate"], item["points_total"], item["name"]),
    )

    behind_plan_students = sorted(
        [
            student
            for student in student_supervision_rows
            if student["halaqa_id"] and (
                not student["plan"]
                or student["attendance_rate"] < 75
                or (
                    student["last_memorization"]
                    and student["last_memorization"].evaluation == "needs_followup"
                )
            )
        ],
        key=lambda item: (
            0 if not item["plan"] else 1,
            item["attendance_rate"],
            item["points_total"],
            item["name"],
        ),
    )
    plan_followup_students = behind_plan_students[:6]
    at_risk_students = [
        student for student in student_supervision_rows if student["at_risk"]
    ][:8]
    students_attention_chart = {
        "labels": [student["name"] for student in weak_attendance_students[:6]] or ["لا توجد حالات حرجة"],
        "values": [student["attendance_rate"] for student in weak_attendance_students[:6]] or [0],
        "is_demo": False,
    }
    plan_overview["needs_followup"] = len(behind_plan_students)

    points_summary = PointTransaction.objects.filter(visible_points_range_filters).aggregate(
        net_total=Coalesce(Sum("value"), 0),
        transaction_total=Count("id"),
        students_covered=Count("student_id", distinct=True),
        deduction_total=Coalesce(Sum("value", filter=Q(value__lt=0)), 0),
    )
    points_overview = {
        "net_total": points_summary["net_total"],
        "transaction_total": points_summary["transaction_total"],
        "students_covered": points_summary["students_covered"],
        "deduction_total": abs(points_summary["deduction_total"]),
    }
    points_leaderboard = sorted(
        student_supervision_rows,
        key=lambda item: (item["points_total"], item["memorized_total"]),
        reverse=True,
    )[:8]
    recent_point_rows = list(
        PointTransaction.objects.filter(visible_points_range_filters)
        .select_related("student", "halaqa")
        .order_by("-date")[:8]
    )

    teacher_note_feed = []
    for attendance in Attendance.objects.filter(visible_attendance_range_filters).exclude(
        notes=""
    ).select_related("student", "session__halaqa").order_by("-session__date", "-id")[:6]:
        teacher_note_feed.append(
            {
                "source": "ملاحظة حضور",
                "subject": attendance.student.name,
                "context": attendance.session.halaqa.name,
                "note": attendance.notes,
                "timestamp": _as_local_midnight(attendance.session.date),
            }
        )
    for homework in Homework.objects.filter(visible_homework_note_filters).exclude(
        assignment_notes=""
    ).filter(
        assigned_date__range=(start_date, end_date)
    ).select_related("student", "halaqa").order_by("-assigned_date", "-id")[:4]:
        teacher_note_feed.append(
            {
                "source": "إسناد واجب",
                "subject": homework.student.name,
                "context": homework.halaqa.name,
                "note": homework.assignment_notes,
                "timestamp": _as_local_midnight(homework.assigned_date),
            }
        )
    for homework in Homework.objects.filter(visible_homework_note_filters).exclude(
        evaluation_notes=""
    ).filter(
        evaluation_date__range=(start_date, end_date)
    ).select_related("student", "halaqa").order_by("-evaluation_date", "-id")[:4]:
        teacher_note_feed.append(
            {
                "source": "تقييم واجب",
                "subject": homework.student.name,
                "context": homework.halaqa.name,
                "note": homework.evaluation_notes,
                "timestamp": _as_local_midnight(homework.evaluation_date),
            }
        )
    for plan in Plan.objects.filter(visible_plan_note_filters).exclude(
        notes=""
    ).filter(
        start_date__range=(start_date, end_date)
    ).select_related("student", "halaqa").order_by("-start_date", "-id")[:4]:
        teacher_note_feed.append(
            {
                "source": "ملاحظة خطة",
                "subject": plan.student.name,
                "context": plan.halaqa.name,
                "note": plan.notes,
                "timestamp": _as_local_midnight(plan.start_date),
            }
        )
    for transaction in PointTransaction.objects.filter(visible_points_range_filters).exclude(
        reason=""
    ).select_related("student", "halaqa").order_by("-date", "-id")[:4]:
        teacher_note_feed.append(
            {
                "source": "سبب نقاط",
                "subject": transaction.student.name,
                "context": transaction.halaqa.name,
                "note": transaction.reason,
                "timestamp": transaction.date,
            }
        )
    if scope_halaqa_ids:
        for session in Session.objects.filter(
            halaqa_id__in=scope_halaqa_ids,
            date__range=(start_date, end_date),
        ).exclude(notes="").select_related("halaqa").order_by("-date", "-id")[:4]:
            teacher_note_feed.append(
                {
                    "source": "ملاحظة جلسة",
                    "subject": session.halaqa.name,
                    "context": session.date.strftime("%Y-%m-%d"),
                    "note": session.notes,
                    "timestamp": _as_local_midnight(session.date),
                }
            )
    teacher_note_feed = sorted(
        teacher_note_feed,
        key=lambda item: item["timestamp"],
        reverse=True,
    )[:12]

    overloaded_halaqas = [
        {
            "name": halaqa.name,
            "students": halaqa.active_student_count,
            "teachers": halaqa.teacher_count,
            "load_state": "مكتظة" if halaqa.active_student_count >= 20 else "مستقرة",
        }
        for halaqa in top_halaqas_rows
        if halaqa.active_student_count or halaqa.teacher_count
    ][:6]

    recent_points = list(
        PointTransaction.objects.filter(points_filters)
        .select_related("student", "halaqa")
        .order_by("-date")[:4]
    )
    recent_memorization = list(
        MemorizationRecord.objects.filter(
            student_id__in=filtered_student_ids or student_ids,
            date__range=(start_date, end_date),
        )
        .select_related("student")
        .order_by("-date")[:4]
    )
    recent_attendance = list(
        Attendance.objects.filter(attendance_filters)
        .select_related("student", "session__halaqa")
        .order_by("-session__date")[:4]
    )

    recent_activity = []
    for entry in recent_points:
        recent_activity.append(
            {
                "title": "حركة نقاط",
                "subject": entry.student.name,
                "detail": f"{entry.value:+} نقطة في {entry.halaqa.name}",
                "timestamp": entry.date,
                "tone": "success" if entry.value >= 0 else "danger",
            }
        )
    for entry in recent_memorization:
        recent_activity.append(
            {
                "title": "تسجيل حفظ",
                "subject": entry.student.name,
                "detail": f"{entry.recitation_title} {entry.recitation_range}".strip(),
                "timestamp": _as_local_midnight(entry.date),
                "tone": "info",
            }
        )
    for entry in recent_attendance:
        recent_activity.append(
            {
                "title": "تسجيل حضور",
                "subject": entry.student.name,
                "detail": f"{entry.session.halaqa.name} - {entry.get_status_display()}",
                "timestamp": _as_local_midnight(entry.session.date),
                "tone": "warning" if entry.status == "absent" else "secondary",
            }
        )
    recent_activity = sorted(
        recent_activity,
        key=lambda item: item["timestamp"],
        reverse=True,
    )[:8]

    pending_approvals = list(
        MemorizationRecord.objects.filter(
            is_approved=False,
            student_id__in=filtered_student_ids or student_ids,
        )
        .select_related("student")
        .order_by("-date")[:6]
    )

    students_without_halaqa_count = sum(1 for summary in student_summaries if not summary["halaqa_id"])
    students_without_category_count = sum(
        1 for summary in student_summaries if not summary["category_resolved"]
    )
    halaqas_without_category_count = sum(
        1 for row in halaqa_supervision_rows if not row["category_resolved"]
    )
    halaqas_without_teachers_count = halaqa_scope.filter(teacher_count=0).count()
    low_attendance_issues_count = len(weak_attendance_students)
    pending_registrations_count = sum(
        1
        for summary in student_summaries
        if summary["created_at"].date() >= start_date and not summary["halaqa_id"]
    )
    missing_parent_access_count = sum(
        1 for summary in student_summaries if not summary["has_parent_access"]
    )

    alerts = [
        {
            "title": "طلاب بلا حلقة",
            "count": students_without_halaqa_count,
            "detail": "تحتاج هذه التسجيلات إلى إسناد داخل حلقة مناسبة.",
            "tone": "danger" if students_without_halaqa_count else "success",
        },
        {
            "title": "طلاب بلا تصنيف",
            "count": students_without_category_count,
            "detail": "هؤلاء الطلاب يحتاجون ربطا واضحا بفئة رسمية أو حلقة تحمل فئة معتمدة.",
            "tone": "warning" if students_without_category_count else "success",
        },
        {
            "title": "حلقات بلا فئة",
            "count": halaqas_without_category_count,
            "detail": "تظهر بوضوح في التقارير حتى لا تختلط بالفئات الرسمية داخل المتابعة الإشرافية.",
            "tone": "warning" if halaqas_without_category_count else "success",
        },
        {
            "title": "حلقات بلا معلمين",
            "count": halaqas_without_teachers_count,
            "detail": "إسناد المعلمين هنا ينعكس مباشرة على ضغط التشغيل.",
            "tone": "danger" if halaqas_without_teachers_count else "success",
        },
        {
            "title": "مخاطر حضور منخفض",
            "count": low_attendance_issues_count,
            "detail": "مبني على حضور أقل من 75% أو حالة متابعة.",
            "tone": "warning" if low_attendance_issues_count else "success",
        },
        {
            "title": "طلبات تسجيل معلقة",
            "count": pending_registrations_count,
            "detail": "يتم احتسابها كطلاب جدد دون حلقة مفعلة.",
            "tone": "warning" if pending_registrations_count else "success",
        },
        {
            "title": "وصول ولي الأمر",
            "count": missing_parent_access_count,
            "detail": "طلاب لديهم ملف دون حساب ولي أمر مرتبط.",
            "tone": "info" if missing_parent_access_count else "success",
        },
    ]

    quick_actions = [
        {
            "title": "إضافة طالب",
            "subtitle": "فتح صفحة التسجيل الحالية",
            "icon": "fa-user-plus",
            "href": reverse("students:dashboard"),
            "tone": "primary",
        },
        {
            "title": "إضافة معلم",
            "subtitle": "عبر لوحة Django الإدارية",
            "icon": "fa-chalkboard-user",
            "href": reverse("admin:halaqas_teacher_add"),
            "tone": "secondary",
        },
        {
            "title": "إضافة حلقة",
            "subtitle": "إنشاء حلقة جديدة بسرعة",
            "icon": "fa-mosque",
            "href": reverse("admin:halaqas_halaqa_add"),
            "tone": "accent",
        },
        {
            "title": "إدارة الفئات",
            "subtitle": "مراجعة الفئات الرسمية وربطها بالحلقات",
            "icon": "fa-layer-group",
            "href": reverse("admin:halaqas_category_changelist"),
            "tone": "warning",
        },
        {
            "title": "مراجعة التسجيلات",
            "subtitle": "التركيز على السجلات غير المكتملة",
            "icon": "fa-user-clock",
            "href": f"{reverse('halaqas:master_admin_dashboard')}?status=unassigned",
            "tone": "danger",
        },
        {
            "title": "توليد التقارير",
            "subtitle": "الانتقال مباشرة إلى التحليلات",
            "icon": "fa-chart-pie",
            "href": "#reportsPanel",
            "tone": "success",
        },
        {
            "title": "إدارة الوصول",
            "subtitle": "حسابات أولياء الأمور والموظفين",
            "icon": "fa-key",
            "href": reverse("admin:auth_user_changelist"),
            "tone": "info",
        },
    ]

    filter_category_options = [
        {
            "value": str(category.id),
            "label": category.name,
            "meta": category.grade_span,
        }
        for category in Category.objects.order_by("display_order", "code")
    ]
    filter_category_options.append(
        {
            "value": UNRESOLVED_CATEGORY_FILTER,
            "label": UNRESOLVED_CATEGORY_LABEL,
            "meta": "طلاب أو حلقات تحتاج استكمال الربط الرسمي",
        }
    )
    filter_student_options = [
        {
            "value": str(student.id),
            "label": student.name,
            "meta": student.halaqa.name if student.halaqa_id else "بلا حلقة",
        }
        for student in student_option_qs
    ]
    scope_label = "على مستوى المعهد بالكامل"
    if student_filter and focused_student:
        scope_label = f"ضمن الطالب: {focused_student['name']}"
    elif halaqa_filter:
        selected_halaqa = all_halaqas.filter(pk=halaqa_filter).first()
        if selected_halaqa:
            scope_label = f"ضمن الحلقة: {selected_halaqa.name}"
    elif teacher_filter:
        selected_teacher = all_teachers.filter(pk=teacher_filter).first()
        if selected_teacher:
            scope_label = f"ضمن المعلم: {selected_teacher.full_name}"
    elif category_filter:
        if category_filter == UNRESOLVED_CATEGORY_FILTER:
            scope_label = f"ضمن النطاق غير المحسوم: {UNRESOLVED_CATEGORY_LABEL}"
        else:
            selected_category = Category.objects.filter(pk=category_filter).first()
            if selected_category:
                scope_label = f"ضمن الفئة: {selected_category.name}"

    greeting_name = "مدير المعهد"
    if request.user.is_authenticated:
        greeting_name = request.user.get_full_name() or request.user.username or greeting_name

    context = {
        "brand_title": "معهد قباء لتحفيظ القرآن الكريم",
        "brand_subtitle": "لوحة الإدارة المركزية",
        "user_label": greeting_name,
        "page_title": "لوحة الإدارة المركزية",
        "page_subtitle": scope_label,
        "hero_actions": quick_actions[:3],
        "foundation_notes": [
            "التصنيفات الآن ممثلة رسميا في بنية المعهد، مع إبقاء الصفحات الحالية متوافقة مع البيانات القديمة والجديدة.",
            "طلبات التسجيل المعلقة تحتسب حاليا كطلاب جدد لم يتم ربطهم بحلقة مفعلة بعد.",
            "الحلقات أو الطلاب غير المرتبطين بفئة رسمية لا تكسر التقارير؛ بل تظهر كحالات متابعة واضحة داخل نفس اللوحة.",
        ],
        "filters": {
            "category": category_filter,
            "halaqa": halaqa_filter,
            "teacher": teacher_filter,
            "student": student_filter,
            "status": status_filter,
            "range": date_range_filter,
            "start_date": start_date.isoformat() if date_range_filter == "custom" else "",
            "end_date": end_date.isoformat() if date_range_filter == "custom" else "",
            "focus_student": focused_student["id"] if focused_student else focus_student_filter,
        },
        "filter_options": {
            "categories": filter_category_options,
            "halaqas": list(all_halaqas),
            "teachers": list(all_teachers),
            "students": filter_student_options,
        },
        "export_controls": {
            "endpoint": reverse("halaqas:master_admin_dashboard_export"),
            "report_options": _get_export_report_options(),
            "level_options": _get_export_level_options(),
            "default_report": "current_view",
            "default_level": "summary",
            "current_panel": request.GET.get("current_panel", "overviewPanel"),
        },
        "date_window_label": _format_date_window_label(start_date, end_date),
        "kpis": kpis,
        "quick_actions": quick_actions,
        "alerts": alerts,
        "latest_registrations": latest_registrations,
        "halaqa_supervision_rows": halaqa_supervision_rows,
        "category_supervision_rows": category_supervision_rows,
        "category_attendance_ranking": category_attendance_ranking[:8],
        "category_memorization_ranking": category_memorization_ranking[:8],
        "category_points_ranking": category_points_ranking[:8],
        "unresolved_category_rows": unresolved_category_rows,
        "strongest_halaqas": strongest_halaqas,
        "weakest_halaqas": weakest_halaqas,
        "student_supervision_rows": student_supervision_rows,
        "focused_student": focused_student,
        "weak_attendance_students": weak_attendance_students[:6],
        "at_risk_students": at_risk_students,
        "top_students": top_students,
        "students_with_active_plans": students_with_active_plans[:6],
        "plan_followup_students": plan_followup_students[:6],
        "plan_overview": plan_overview,
        "recent_plan_rows": recent_plan_rows,
        "homework_overview": homework_overview,
        "recent_homework_rows": recent_homework_rows,
        "pending_homework_rows": pending_homework_rows,
        "overloaded_halaqas": overloaded_halaqas,
        "recent_activity": recent_activity,
        "points_overview": points_overview,
        "points_leaderboard": points_leaderboard,
        "recent_point_rows": recent_point_rows,
        "teacher_note_feed": teacher_note_feed,
        "pending_approvals": pending_approvals,
        "category_foundation": {
            "derived_count": total_categories,
            "missing_count": students_without_category_count,
            "halaqa_missing_count": halaqas_without_category_count,
            "access_count": missing_parent_access_count,
        },
        "charts": {
            "students_by_category": students_by_category_chart,
            "students_by_halaqa": students_by_halaqa_chart,
            "attendance_trends": attendance_trends_chart,
            "performance_trends": performance_trends_chart,
            "teacher_distribution": teacher_distribution_chart,
            "top_halaqas": top_halaqas_chart,
            "students_attention": students_attention_chart,
        },
    }
    return context


@staff_member_required
def master_admin_dashboard(request):
    context = _build_master_admin_dashboard_context(request)
    return render(request, "halaqas/admin/dashboard.html", context)


@staff_member_required
def master_admin_dashboard_export(request):
    context = _build_master_admin_dashboard_context(request)
    requested_format = request.GET.get("format", "print")
    level = request.GET.get("level", "summary")
    if level not in {"summary", "detailed"}:
        level = "summary"

    current_panel = request.GET.get("current_panel", "overviewPanel")
    report_key = _resolve_export_report_key(
        request.GET.get("report", "current_view"),
        current_panel,
    )
    export_package = _build_admin_dashboard_export_package(context, report_key)
    if requested_format == "csv":
        return _build_admin_dashboard_csv_response(context, export_package, level)

    level_label = "ملخص" if level == "summary" else "تفصيلي"
    export_context = {
        "brand_title": context["brand_title"],
        "brand_subtitle": context["brand_subtitle"],
        "page_title": context["page_title"],
        "page_subtitle": context["page_subtitle"],
        "date_window_label": context["date_window_label"],
        "report_title": export_package["title"],
        "report_subtitle": export_package["subtitle"],
        "summary_cards": export_package["summary_cards"],
        "tables": export_package["summary_tables"] if level == "summary" else export_package["detail_tables"],
        "scope_rows": _build_export_scope_rows(context, export_package["title"], level_label),
        "level_label": level_label,
        "export_format": requested_format,
        "auto_print": requested_format == "pdf",
        "dashboard_url": _dashboard_url(
            reverse("halaqas:master_admin_dashboard"),
            context["filters"],
            fragment=current_panel,
        ),
    }
    return render(request, "halaqas/admin/dashboard_export.html", export_context)
