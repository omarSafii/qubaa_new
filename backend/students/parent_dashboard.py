from collections import defaultdict
from datetime import timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from django.utils.dateparse import parse_date

from halaqas.models import Attendance, Homework, Plan, PointTransaction
from .models import MemorizationRecord


PAGE_SIZE = 10
DEFAULT_PERIOD = "90"
PERIOD_DAY_OPTIONS = {
    "30": 30,
    "90": 90,
    "180": 180,
    "all": None,
}
VALID_TABS = {"memorization", "plan", "attendance", "homework", "points", "charts"}


def _normalized_period(request, *, has_custom_dates):
    period = (request.GET.get("period", "") or "").strip()
    legacy_scope = (request.GET.get("scope", "") or "").strip()

    if period in PERIOD_DAY_OPTIONS:
        return period
    if has_custom_dates:
        return DEFAULT_PERIOD
    if legacy_scope == "all":
        return "all"
    return DEFAULT_PERIOD


def _range_from_request(request):
    today = timezone.localdate()
    start = parse_date(request.GET.get("start_date", "") or request.GET.get("from_date", ""))
    end = parse_date(request.GET.get("end_date", "") or request.GET.get("to_date", ""))
    has_custom_dates = bool(start or end)
    period = _normalized_period(request, has_custom_dates=has_custom_dates)

    if has_custom_dates:
        start = start or today - timedelta(days=PERIOD_DAY_OPTIONS[DEFAULT_PERIOD] - 1)
        end = min(end or today, today)
        if start > end:
            start, end = end, start
        return period, start, end, True

    if period == "all":
        return period, None, None, False

    period_days = PERIOD_DAY_OPTIONS[period]
    start = today - timedelta(days=period_days - 1)
    return period, start, today, False


def _within_range(queryset, field, start, end):
    if start:
        queryset = queryset.filter(**{f"{field}__gte": start})
    if end:
        queryset = queryset.filter(**{f"{field}__lte": end})
    return queryset


def _absence_message(row, empty_message):
    if row["is_absent"]:
        return "الطالب غائب، لذلك لا توجد بيانات لهذا اليوم"
    return empty_message


def build_parent_daily_log(*, student, halaqa, request):
    period, start, end, uses_custom_dates = _range_from_request(request)
    active_tab = request.GET.get("tab", "memorization")
    if active_tab not in VALID_TABS:
        active_tab = "memorization"

    attendance = Attendance.objects.none()
    points = PointTransaction.objects.none()
    plans = Plan.objects.none()
    homeworks = Homework.objects.none()
    if halaqa:
        attendance = Attendance.objects.filter(
            student=student,
            session__halaqa=halaqa,
        ).select_related("session", "recorded_by")
        points = PointTransaction.objects.filter(student=student, halaqa=halaqa)
        plans = Plan.objects.filter(student=student, halaqa=halaqa)
        homeworks = Homework.objects.filter(student=student, halaqa=halaqa)

    memorization = MemorizationRecord.objects.filter(student=student).select_related("homework")

    attendance_dates = _within_range(attendance, "session__date", start, end).values_list(
        "session__date", flat=True
    )
    memorization_dates = _within_range(memorization, "date", start, end).values_list("date", flat=True)
    point_dates = _within_range(
        points.annotate(day=TruncDate("date")), "day", start, end
    ).values_list("day", flat=True)
    plan_dates = _within_range(plans, "start_date", start, end).values_list("start_date", flat=True)
    homework_assigned_dates = _within_range(homeworks, "assigned_date", start, end).values_list(
        "assigned_date", flat=True
    )
    homework_evaluated_dates = _within_range(
        homeworks.exclude(evaluation_date__isnull=True), "evaluation_date", start, end
    ).values_list("evaluation_date", flat=True)

    activity_days = sorted(
        {
            *attendance_dates,
            *memorization_dates,
            *point_dates,
            *plan_dates,
            *homework_assigned_dates,
            *homework_evaluated_dates,
        },
        reverse=True,
    )
    paginator = Paginator(activity_days, PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page", 1))
    page_days = list(page_obj.object_list)

    rows = {
        day: {
            "date": day,
            "attendance": [],
            "memorization": [],
            "points": [],
            "plans": [],
            "homeworks": [],
            "is_absent": False,
            "attendance_status": "",
            "points_total": None,
        }
        for day in page_days
    }

    if page_days:
        for item in attendance.filter(session__date__in=page_days).order_by("-session__date", "-id"):
            rows[item.session.date]["attendance"].append(item)
        for item in memorization.filter(date__in=page_days).order_by("-date", "-id"):
            rows[item.date]["memorization"].append(item)
        for item in points.filter(date__date__in=page_days).order_by("-date", "-id"):
            rows[timezone.localtime(item.date).date()]["points"].append(item)
        for item in plans.filter(start_date__in=page_days).order_by("-start_date", "-id"):
            rows[item.start_date]["plans"].append(item)
        for item in homeworks.filter(
            Q(assigned_date__in=page_days) | Q(evaluation_date__in=page_days)
        ).order_by("-assigned_date", "-id"):
            if item.assigned_date in rows:
                rows[item.assigned_date]["homeworks"].append(
                    {"record": item, "event": "assigned", "label": "تم إسناد الواجب"}
                )
            if item.evaluation_date in rows and item.evaluation_date != item.assigned_date:
                rows[item.evaluation_date]["homeworks"].append(
                    {"record": item, "event": "evaluated", "label": "تم تقييم الواجب"}
                )

    daily_rows = []
    for day in page_days:
        row = rows[day]
        statuses = [item.status for item in row["attendance"]]
        row["is_absent"] = "absent" in statuses and "present" not in statuses
        row["attendance_status"] = "، ".join(
            dict.fromkeys(item.get_status_display() for item in row["attendance"])
        )
        if row["points"]:
            row["points_total"] = sum(item.value for item in row["points"])
        row["memorization_message"] = _absence_message(row, "لم يُسجل تسميع لهذا اليوم")
        row["plan_message"] = _absence_message(row, "لا يوجد تحديث للخطة في هذا اليوم")
        row["homework_message"] = _absence_message(row, "لم يُسجل واجب لهذا اليوم")
        row["points_message"] = _absence_message(row, "لم تُسجل نقاط لهذا اليوم")
        row["attendance_message"] = "لم تُسجل حالة الحضور لهذا اليوم"
        daily_rows.append(row)

    latest_recitation = memorization.order_by("-date", "-id").first()
    next_homework = homeworks.filter(evaluation_date__isnull=True).order_by(
        "expected_recitation_date", "-assigned_date", "-id"
    ).first()

    preserved = {
        "period": period,
        "tab": active_tab,
    }
    if uses_custom_dates:
        preserved["start_date"] = start.isoformat() if start else ""
        preserved["end_date"] = end.isoformat() if end else ""
    filter_query = urlencode({key: value for key, value in preserved.items() if value})

    return {
        "rows": daily_rows,
        "page_obj": page_obj,
        "active_tab": active_tab,
        "period": period,
        "uses_custom_dates": uses_custom_dates,
        "filter_query": filter_query,
        "latest_recitation": latest_recitation,
        "next_homework": next_homework,
        "is_empty": not activity_days,
        "total_days": len(activity_days),
        "period_options": [
            {"value": "30", "label": "آخر 30 يومًا"},
            {"value": "90", "label": "آخر 90 يومًا"},
            {"value": "180", "label": "آخر 180 يومًا"},
            {"value": "all", "label": "الكل"},
        ],
    }
