from collections import defaultdict
from datetime import date, datetime, time, timedelta
import re

from django.db.models import Count, ExpressionWrapper, F, IntegerField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from halaqas.models import Attendance, Halaqa, HalaqaMembership, Homework, Plan, PointTransaction, Session, Teacher
from .models import MemorizationRecord, Student
from .serializers import MemorizationRecordSerializer, StudentRegistrationSerializer, StudentSerializer


VERSE_COUNT_EXPR = ExpressionWrapper(
    F('to_verse') - F('from_verse') + Value(1),
    output_field=IntegerField(),
)
AVERAGE_VERSES_PER_PAGE = 20
ATTENDANCE_SCORE_MAP = {
    'present': 100,
    'excused': 60,
    'absent': 0,
}
MEMORIZATION_EVALUATION_SCORE_MAP = {
    'excellent': 4,
    'very_good': 3,
    'good': 2,
    'needs_followup': 1,
}
HOMEWORK_EVALUATION_SCORE_MAP = {
    'excellent': 4,
    'completed': 3,
    'partial': 2,
    'not_completed': 1,
}


def _estimate_pages(verses_total):
    return round((verses_total or 0) / AVERAGE_VERSES_PER_PAGE, 1)


def _estimate_recited_pages(record):
    pages_text = (record.pages or '').strip()
    if pages_text:
        numbers = [int(value) for value in re.findall(r'\d+', pages_text)]
        if not numbers:
            return 1
        if '-' in pages_text and len(numbers) >= 2:
            start_page, end_page = numbers[0], numbers[1]
            if end_page >= start_page:
                return (end_page - start_page) + 1
        if '/' in pages_text and len(numbers) >= 2:
            return len(set(numbers))
        return 1

    return _estimate_pages(record.verses_count)


def _month_bounds(day_value):
    month_start = day_value.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    return month_start, month_end


def _week_start(day_value):
    return day_value - timedelta(days=(day_value.weekday() - 5) % 7)


def _infer_category(grade):
    if hasattr(grade, 'category_id') and getattr(grade, 'category_id', None):
        return grade.category.name
    if hasattr(grade, 'get_category_label'):
        return grade.get_category_label()

    grade_text = (grade or '').strip()
    if 'ابتدائي' in grade_text:
        return 'المرحلة الابتدائية'
    if 'متوسط' in grade_text:
        return 'المرحلة المتوسطة'
    if 'ثانوي' in grade_text:
        return 'المرحلة الثانوية'
    return 'غير مصنف'


def _status_label(status):
    return {
        'present': 'حاضر',
        'absent': 'غائب',
        'excused': 'معذور',
    }.get(status, 'غير مسجل')


def _attendance_source_label(attendance):
    return {
        'teacher': 'المصدر: الأستاذ',
        'supervisor': 'المصدر: الموجه',
        'admin': 'المصدر: الإدارة',
    }.get(getattr(attendance, 'recorded_by_role', ''), '')


def _homework_status(homework, reference_date):
    if not homework:
        return 'none'
    if homework.evaluation_date and homework.evaluation_date <= reference_date:
        return 'evaluated'
    if homework.assigned_date == reference_date:
        return 'assigned'
    return 'pending'


def _homework_status_label(status):
    return {
        'assigned': 'تم الإسناد',
        'pending': 'بانتظار التقييم',
        'evaluated': 'تم التقييم',
        'none': 'لا يوجد',
    }.get(status, 'لا يوجد')


def _resolve_month_value(raw_month, fallback_day):
    if raw_month:
        try:
            year, month = raw_month.split('-', 1)
            return date(int(year), int(month), 1)
        except (TypeError, ValueError):
            pass
    return fallback_day.replace(day=1)


def _resolve_report_range(request, today):
    raw_range = request.GET.get('range', 'month')
    raw_month = request.GET.get('month', '')
    raw_start = request.GET.get('start_date', '')
    raw_end = request.GET.get('end_date', '')

    if raw_range == 'today':
        start_date = today
        end_date = today
        label = f'تقرير اليوم {today.isoformat()}'
    elif raw_range == 'week':
        start_date = _week_start(today)
        end_date = today
        label = f'هذا الأسبوع من {start_date.isoformat()} إلى {end_date.isoformat()}'
    elif raw_range == 'selected_month':
        month_start = _resolve_month_value(raw_month, today)
        start_date, end_date = _month_bounds(month_start)
        if start_date > today:
            start_date, end_date = _month_bounds(today)
        end_date = min(end_date, today) if start_date.year == today.year and start_date.month == today.month else end_date
        label = f'شهر {start_date.strftime("%Y-%m")}'
    elif raw_range == 'custom':
        parsed_start = parse_date(raw_start)
        parsed_end = parse_date(raw_end)
        if parsed_start and parsed_end:
            if parsed_start > parsed_end:
                parsed_start, parsed_end = parsed_end, parsed_start
            start_date = parsed_start
            end_date = min(parsed_end, today)
            label = f'فترة مخصصة من {start_date.isoformat()} إلى {end_date.isoformat()}'
        else:
            raw_range = 'month'
            start_date, _ = _month_bounds(today)
            end_date = today
            label = f'هذا الشهر حتى {today.isoformat()}'
    else:
        raw_range = 'month'
        start_date, _ = _month_bounds(today)
        end_date = today
        label = f'هذا الشهر حتى {today.isoformat()}'

    return {
        'key': raw_range,
        'start': start_date,
        'end': end_date,
        'label': label,
        'selected_month': _resolve_month_value(raw_month, today).strftime('%Y-%m'),
        'start_value': raw_start or start_date.isoformat(),
        'end_value': raw_end or end_date.isoformat(),
    }


def _day_list(start_date, end_date):
    total_days = (end_date - start_date).days + 1
    return [start_date + timedelta(days=index) for index in range(total_days)]


def _day_labels(days):
    return [day.strftime('%m/%d') for day in days]


def _max_candidate(candidates):
    valid_candidates = [item for item in candidates if item[0] is not None]
    return max(valid_candidates, key=lambda item: item[0], default=(None, ''))


def _date_to_noon(day_value):
    return timezone.make_aware(
        datetime.combine(day_value, time(12, 0)),
        timezone.get_current_timezone(),
    )


def _attendance_summary_from_records(records):
    present = sum(1 for item in records if item.status == 'present')
    absent = sum(1 for item in records if item.status == 'absent')
    excused = sum(1 for item in records if item.status == 'excused')
    total = present + absent + excused
    percentage = round((present / total) * 100) if total else 0
    return {
        'present': present,
        'absent': absent,
        'excused': excused,
        'total': total,
        'percentage': percentage,
    }


def _build_homework_snapshot(homework, reference_date):
    if not homework:
        return {
            'exists': False,
            'status': 'none',
            'status_label': _homework_status_label('none'),
            'title': 'لا يوجد واجب مسجل',
            'meta_text': 'لا يوجد واجب مسجل',
            'detail_text': 'يظهر هنا آخر واجب يسنده المعلم للطالب.',
            'assigned_date': '',
            'evaluation_date': '',
            'evaluation_label': '',
            'teacher_note': '',
            'assignment_type_label': '',
            'assignment_text': '',
            'expected_recitation_date': '',
        }

    status = _homework_status(homework, reference_date)
    title = f'{homework.get_assignment_type_display()}: {homework.assignment_text}'
    teacher_note = homework.evaluation_notes or homework.assignment_notes
    if status == 'evaluated' and homework.evaluation_date:
        detail_text = f'{homework.get_evaluation_display()} - {homework.evaluation_date.isoformat()}'
    else:
        detail_text = f'أُسند في {homework.assigned_date.isoformat()}'
        if homework.expected_recitation_date:
            detail_text = f'{detail_text}، التسميع المتوقع {homework.expected_recitation_date.isoformat()}'
    return {
        'exists': True,
        'status': status,
        'status_label': _homework_status_label(status),
        'title': title,
        'meta_text': title,
        'detail_text': detail_text,
        'assigned_date': homework.assigned_date.isoformat(),
        'evaluation_date': homework.evaluation_date.isoformat() if homework.evaluation_date else '',
        'evaluation_label': homework.get_evaluation_display() if homework.evaluation else '',
        'teacher_note': teacher_note,
        'assignment_type_label': homework.get_assignment_type_display(),
        'assignment_text': homework.assignment_text,
        'expected_recitation_date': (
            homework.expected_recitation_date.isoformat() if homework.expected_recitation_date else ''
        ),
    }


def _average_choice_score(records, *, value_getter, score_map):
    scores = []
    for record in records:
        value = value_getter(record)
        if value in score_map:
            scores.append(score_map[value])
    return round(sum(scores) / len(scores), 1) if scores else 0


def _comparison_periods(reference_date, window_days=14):
    recent_end = reference_date
    recent_start = reference_date - timedelta(days=window_days - 1)
    previous_end = recent_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=window_days - 1)
    return recent_start, recent_end, previous_start, previous_end


def _trend_meta(direction):
    return {
        'up': {
            'label': 'مسار صاعد',
            'icon': 'fas fa-arrow-trend-up',
            'badge_class': 'ok',
        },
        'down': {
            'label': 'مسار متراجع',
            'icon': 'fas fa-arrow-trend-down',
            'badge_class': 'bad',
        },
        'flat': {
            'label': 'مسار مستقر',
            'icon': 'fas fa-arrows-left-right',
            'badge_class': 'mutep',
        },
    }[direction]


def _compare_metric(current_value, previous_value, *, tolerance=0):
    if current_value > previous_value + tolerance:
        return 1
    if current_value < previous_value - tolerance:
        return -1
    return 0


def _range_label(start_date, end_date):
    return f'{start_date.isoformat()} إلى {end_date.isoformat()}'


def _build_general_performance_trend(reference_date, attendance_records, point_transactions, homeworks, window_days=14):
    recent_start, recent_end, previous_start, previous_end = _comparison_periods(reference_date, window_days)

    recent_attendance = [
        item for item in attendance_records
        if recent_start <= item.session.date <= recent_end
    ]
    previous_attendance = [
        item for item in attendance_records
        if previous_start <= item.session.date <= previous_end
    ]
    recent_points = [
        item for item in point_transactions
        if recent_start <= item.date.date() <= recent_end
    ]
    previous_points = [
        item for item in point_transactions
        if previous_start <= item.date.date() <= previous_end
    ]
    recent_homework_evaluations = [
        item for item in homeworks
        if item.evaluation_date and recent_start <= item.evaluation_date <= recent_end
    ]
    previous_homework_evaluations = [
        item for item in homeworks
        if item.evaluation_date and previous_start <= item.evaluation_date <= previous_end
    ]

    recent_attendance_summary = _attendance_summary_from_records(recent_attendance)
    previous_attendance_summary = _attendance_summary_from_records(previous_attendance)
    recent_points_total = sum(item.value for item in recent_points)
    previous_points_total = sum(item.value for item in previous_points)
    recent_homework_avg = _average_choice_score(
        recent_homework_evaluations,
        value_getter=lambda item: item.evaluation,
        score_map=HOMEWORK_EVALUATION_SCORE_MAP,
    )
    previous_homework_avg = _average_choice_score(
        previous_homework_evaluations,
        value_getter=lambda item: item.evaluation,
        score_map=HOMEWORK_EVALUATION_SCORE_MAP,
    )

    signals = []
    attendance_change = _compare_metric(
        recent_attendance_summary['percentage'],
        previous_attendance_summary['percentage'],
        tolerance=4,
    )
    if attendance_change:
        signals.append(('الحضور', attendance_change))

    points_change = _compare_metric(recent_points_total, previous_points_total, tolerance=1)
    if points_change:
        signals.append(('النقاط', points_change))

    if recent_homework_evaluations or previous_homework_evaluations:
        homework_change = _compare_metric(recent_homework_avg, previous_homework_avg, tolerance=0.24)
        if homework_change:
            signals.append(('نتائج الواجب', homework_change))

    positive_signals = sum(1 for _, direction in signals if direction > 0)
    negative_signals = sum(1 for _, direction in signals if direction < 0)
    direction = 'flat'
    if positive_signals > negative_signals:
        direction = 'up'
    elif negative_signals > positive_signals:
        direction = 'down'

    signal_summary = 'المؤشرات قريبة من الفترة السابقة.'
    if signals:
        signal_summary = ' | '.join(
            f'{label} {"تحسن" if change > 0 else "انخفض"}'
            for label, change in signals
        )

    return {
        **_trend_meta(direction),
        'title': 'الأداء العام',
        'description': 'مبني على سجلات الحضور والنقاط ونتائج الواجب التي يدخلها المعلم.',
        'recent_label': _range_label(recent_start, recent_end),
        'previous_label': _range_label(previous_start, previous_end),
        'recent_summary': (
            f'الحضور {recent_attendance_summary["percentage"]}% | '
            f'صافي النقاط {recent_points_total:+} | '
            f'تقييم واجبات {len(recent_homework_evaluations)}'
        ),
        'previous_summary': (
            f'الحضور {previous_attendance_summary["percentage"]}% | '
            f'صافي النقاط {previous_points_total:+} | '
            f'تقييم واجبات {len(previous_homework_evaluations)}'
        ),
        'signal_summary': signal_summary,
    }


def _build_memorization_trend(reference_date, memorization_records, window_days=14):
    recent_start, recent_end, previous_start, previous_end = _comparison_periods(reference_date, window_days)

    recent_records = [
        item for item in memorization_records
        if recent_start <= item.date <= recent_end
    ]
    previous_records = [
        item for item in memorization_records
        if previous_start <= item.date <= previous_end
    ]

    recent_verses_total = sum(item.verses_count for item in recent_records)
    previous_verses_total = sum(item.verses_count for item in previous_records)
    recent_eval_avg = _average_choice_score(
        recent_records,
        value_getter=lambda item: item.evaluation,
        score_map=MEMORIZATION_EVALUATION_SCORE_MAP,
    )
    previous_eval_avg = _average_choice_score(
        previous_records,
        value_getter=lambda item: item.evaluation,
        score_map=MEMORIZATION_EVALUATION_SCORE_MAP,
    )

    signals = []
    verses_change = _compare_metric(recent_verses_total, previous_verses_total, tolerance=1)
    if verses_change:
        signals.append(('كمية الحفظ', verses_change))

    records_change = _compare_metric(len(recent_records), len(previous_records), tolerance=0)
    if records_change:
        signals.append(('عدد التسميعات', records_change))

    if recent_eval_avg or previous_eval_avg:
        evaluation_change = _compare_metric(recent_eval_avg, previous_eval_avg, tolerance=0.24)
        if evaluation_change:
            signals.append(('جودة التسميع', evaluation_change))

    positive_signals = sum(1 for _, direction in signals if direction > 0)
    negative_signals = sum(1 for _, direction in signals if direction < 0)
    direction = 'flat'
    if positive_signals > negative_signals:
        direction = 'up'
    elif negative_signals > positive_signals:
        direction = 'down'

    signal_summary = 'الحفظ مستقر قياساً بالفترة السابقة.'
    if signals:
        signal_summary = ' | '.join(
            f'{label} {"تحسنت" if change > 0 else "انخفضت"}'
            for label, change in signals
        )

    return {
        **_trend_meta(direction),
        'title': 'مسار التسميع',
        'description': 'مبني على سجلات التسميع وتقييماتها المدخلة في الحلقة.',
        'recent_label': _range_label(recent_start, recent_end),
        'previous_label': _range_label(previous_start, previous_end),
        'recent_summary': (
            f'{len(recent_records)} تسميعات | '
            f'{recent_verses_total} آية | '
            f'متوسط التقييم {recent_eval_avg or 0}/4'
        ),
        'previous_summary': (
            f'{len(previous_records)} تسميعات | '
            f'{previous_verses_total} آية | '
            f'متوسط التقييم {previous_eval_avg or 0}/4'
        ),
        'signal_summary': signal_summary,
    }


def _build_plan_progress(plan, memorization_records, reference_date):
    if not plan:
        return {
            'status': 'none',
            'status_label': 'لا توجد خطة حالية',
            'badge_class': 'muted',
            'expected_percent': 0,
            'actual_percent': 0,
            'total_pages': 0,
            'completed_pages': 0,
            'remaining_pages': 0,
            'remaining_days': 0,
            'required_pages_per_day': 0,
            'target': '',
            'date_range': '',
            'notes': '',
            'labels': [],
            'expected_values': [],
            'actual_values': [],
        }

    plan_start = plan.start_date
    plan_end = plan.end_date
    total_days = max((plan_end - plan_start).days + 1, 1)
    effective_end = min(reference_date, plan_end)
    elapsed_days = 0 if effective_end < plan_start else (effective_end - plan_start).days + 1
    expected_ratio = min(elapsed_days / total_days, 1)
    total_pages = plan.total_pages or 0
    plan_records = [
        record for record in memorization_records
        if plan_start <= record.date <= effective_end
    ]

    if total_pages:
        completed_pages = min(
            sum(_estimate_recited_pages(record) for record in plan_records),
            total_pages,
        )
        actual_ratio = completed_pages / total_pages
    else:
        active_days = {record.date for record in plan_records}
        completed_pages = len(active_days)
        actual_ratio = min(completed_pages / total_days, 1)

    remaining_pages = max(total_pages - completed_pages, 0) if total_pages else 0
    remaining_days = max((plan_end - reference_date).days, 0)
    required_pages_per_day = (
        round(remaining_pages / remaining_days, 1)
        if total_pages and remaining_pages and remaining_days > 0 else 0
    )

    if reference_date < plan_start:
        status = 'not_started'
        status_label = 'لم تبدأ بعد'
        badge_class = 'muted'
    elif plan.is_completed:
        status = 'completed'
        status_label = 'مكتملة'
        badge_class = 'excellent'
        expected_ratio = 1
        actual_ratio = 1
        if total_pages:
            completed_pages = total_pages
            remaining_pages = 0
            required_pages_per_day = 0
    elif actual_ratio >= min(expected_ratio + 0.1, 1):
        status = 'ahead'
        status_label = 'متقدم'
        badge_class = 'excellent'
    elif actual_ratio + 0.08 >= expected_ratio:
        status = 'on_track'
        status_label = 'على المسار'
        badge_class = 'good'
    else:
        status = 'behind'
        status_label = 'متأخر'
        badge_class = 'warning'

    chart_days = _day_list(plan_start, plan_end)
    expected_values = []
    actual_values = []
    cumulative_active_days = set()
    cumulative_pages = 0
    for chart_day in chart_days:
        elapsed = (chart_day - plan_start).days + 1
        expected_values.append(round(min(elapsed / total_days, 1) * 100))
        day_records = [
            record for record in memorization_records
            if record.date == chart_day and plan_start <= record.date <= plan_end
        ]
        if total_pages:
            cumulative_pages = min(
                cumulative_pages + sum(_estimate_recited_pages(record) for record in day_records),
                total_pages,
            )
            actual_values.append(round((cumulative_pages / total_pages) * 100))
        else:
            cumulative_active_days.update(record.date for record in day_records)
            actual_values.append(round((len(cumulative_active_days) / total_days) * 100))

    return {
        'status': status,
        'status_label': status_label,
        'badge_class': badge_class,
        'expected_percent': round(expected_ratio * 100),
        'actual_percent': round(actual_ratio * 100),
        'total_pages': total_pages,
        'completed_pages': round(completed_pages, 1) if completed_pages % 1 else int(completed_pages),
        'remaining_pages': round(remaining_pages, 1) if remaining_pages % 1 else int(remaining_pages),
        'remaining_days': remaining_days,
        'required_pages_per_day': required_pages_per_day,
        'target': plan.target,
        'date_range': f'{plan.start_date.isoformat()} إلى {plan.end_date.isoformat()}',
        'notes': plan.notes,
        'labels': [day.strftime('%m/%d') for day in chart_days],
        'expected_values': expected_values,
        'actual_values': actual_values,
    }


def _build_timeline(start_date, end_date, attendance_records, point_transactions, memorization_records, homeworks, plans, sessions):
    timeline = defaultdict(lambda: {
        'date': None,
        'display_date': '',
        'attendance': None,
        'attendance_note': '',
        'attendance_source': '',
        'session_note': '',
        'points': [],
        'memorization': [],
        'homework': [],
        'plans': [],
        'notes': [],
    })

    def ensure_entry(day_value):
        entry = timeline[day_value]
        entry['date'] = day_value
        entry['display_date'] = day_value.isoformat()
        return entry

    for session in sessions:
        if session.notes:
            entry = ensure_entry(session.date)
            entry['session_note'] = session.notes
            entry['notes'].append({'source': 'ملاحظة الجلسة', 'text': session.notes})

    for attendance in attendance_records:
        entry = ensure_entry(attendance.session.date)
        entry['attendance'] = _status_label(attendance.status)
        entry['attendance_note'] = attendance.notes
        entry['attendance_source'] = _attendance_source_label(attendance)
        if attendance.notes:
            entry['notes'].append({'source': 'ملاحظة الحضور', 'text': attendance.notes})

    for transaction in point_transactions:
        entry = ensure_entry(transaction.date.date())
        entry['points'].append({
            'value': transaction.value,
            'reason': transaction.reason,
            'time': timezone.localtime(transaction.date).strftime('%H:%M'),
        })

    for record in memorization_records:
        entry = ensure_entry(record.date)
        entry['memorization'].append({
            'surah': record.recitation_title,
            'range': record.recitation_range,
            'evaluation': record.get_evaluation_display() if record.evaluation else 'بدون تقييم',
            'pages': _estimate_pages(record.verses_count),
            'source': record.get_recitation_type_display(),
            'note': record.notes,
        })

    for homework in homeworks:
        if start_date <= homework.assigned_date <= end_date:
            entry = ensure_entry(homework.assigned_date)
            entry['homework'].append({
                'kind': 'assigned',
                'title': f'إسناد واجب {homework.get_assignment_type_display()}',
                'text': homework.assignment_text,
                'note': homework.assignment_notes,
            })
            if homework.assignment_notes:
                entry['notes'].append({'source': 'ملاحظة الواجب', 'text': homework.assignment_notes})
        if homework.evaluation_date and start_date <= homework.evaluation_date <= end_date:
            entry = ensure_entry(homework.evaluation_date)
            entry['homework'].append({
                'kind': 'evaluated',
                'title': 'تقييم الواجب',
                'text': homework.get_evaluation_display(),
                'note': homework.evaluation_notes,
            })
            if homework.evaluation_notes:
                entry['notes'].append({'source': 'ملاحظة تقييم الواجب', 'text': homework.evaluation_notes})

    for plan in plans:
        if start_date <= plan.start_date <= end_date:
            entry = ensure_entry(plan.start_date)
            entry['plans'].append({
                'title': 'بداية الخطة',
                'target': plan.target,
                'range': f'{plan.start_date.isoformat()} إلى {plan.end_date.isoformat()}',
            })
            if plan.notes:
                entry['notes'].append({'source': 'ملاحظة الخطة', 'text': plan.notes})

    entries = []
    for day_value in sorted(timeline.keys(), reverse=True):
        entry = timeline[day_value]
        entry['points_total'] = sum(item['value'] for item in entry['points'])
        entry['memorization_count'] = len(entry['memorization'])
        entry['homework_count'] = len(entry['homework'])
        entries.append(entry)
    return entries


def _build_teacher_notes(attendance_records, homeworks, plans, sessions, start_date, end_date):
    notes = []
    for session in sessions:
        if session.notes:
            notes.append({
                'date': session.date,
                'source': 'الجلسة',
                'text': session.notes,
            })
    for attendance in attendance_records:
        if attendance.notes:
            notes.append({
                'date': attendance.session.date,
                'source': _attendance_source_label(attendance) or 'الحضور',
                'text': attendance.notes,
            })
    for homework in homeworks:
        if homework.assignment_notes and start_date <= homework.assigned_date <= end_date:
            notes.append({
                'date': homework.assigned_date,
                'source': 'الواجب',
                'text': homework.assignment_notes,
            })
        if homework.evaluation_notes and homework.evaluation_date and start_date <= homework.evaluation_date <= end_date:
            notes.append({
                'date': homework.evaluation_date,
                'source': 'تقييم الواجب',
                'text': homework.evaluation_notes,
            })
    for plan in plans:
        if plan.notes:
            notes.append({
                'date': plan.start_date,
                'source': 'الخطة',
                'text': plan.notes,
            })
    return sorted(notes, key=lambda item: item['date'], reverse=True)


class StudentViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Student.objects.all()
    lookup_field = 'access_token'
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action == 'create':
            return StudentRegistrationSerializer
        return StudentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        full_access_url = request.build_absolute_uri(
            reverse('students:students_data', args=[student.access_token])
        )
        return Response({
            "msg": "تم تسجيل الطالب بنجاح",
            "student_id": student.id,
            "access_token": str(student.access_token),
            "access_link": full_access_url,
        }, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        today = timezone.localdate()
        report_range = _resolve_report_range(request, today)
        selected_end = min(report_range['end'], today)

        token = kwargs['access_token']
        student = get_object_or_404(Student.objects.select_related('parent'), access_token=token)

        membership = HalaqaMembership.objects.filter(
            student=student,
            is_active=True,
        ).select_related('halaqa').order_by('-join_date', '-id').first()
        halaqa = Halaqa.objects.filter(pk=membership.halaqa_id).first() if membership else None

        attendance_qs = Attendance.objects.none()
        points_qs = PointTransaction.objects.none()
        plans_qs = Plan.objects.none()
        homeworks_qs = Homework.objects.none()
        sessions_qs = Session.objects.none()

        if halaqa:
            attendance_qs = Attendance.objects.filter(
                student=student,
                session__halaqa=halaqa,
            ).select_related('session__halaqa', 'recorded_by').order_by('-session__date', '-id')
            points_qs = PointTransaction.objects.filter(
                student=student,
                halaqa=halaqa,
            ).order_by('-date', '-id')
            plans_qs = Plan.objects.filter(
                student=student,
                halaqa=halaqa,
            ).order_by('-start_date', '-id')
            homeworks_qs = Homework.objects.filter(
                student=student,
                halaqa=halaqa,
            ).order_by('-assigned_date', '-id')
            sessions_qs = Session.objects.filter(
                halaqa=halaqa,
            ).order_by('-date', '-start_time')

        memorization_qs = MemorizationRecord.objects.filter(
            student=student,
        ).order_by('-date', '-id')

        all_attendance = list(attendance_qs)
        all_points = list(points_qs)
        all_memorization = list(memorization_qs)
        all_plans = list(plans_qs)
        all_homeworks = list(homeworks_qs)
        all_sessions = list(sessions_qs)
        for attendance in all_attendance:
            attendance.source_label = _attendance_source_label(attendance)

        teacher_names = []
        if halaqa:
            teacher_names = list(
                Teacher.objects.filter(halaqas=halaqa)
                .order_by('full_name')
                .values_list('full_name', flat=True)
            )
        if not teacher_names:
            teacher_user_ids = {
                user_id
                for user_id in [
                    *(item.created_by_id for item in all_points),
                    *(item.created_by_id for item in all_homeworks),
                    *(item.evaluated_by_id for item in all_homeworks),
                ]
                if user_id
            }
            if teacher_user_ids:
                teacher_names = list(
                    Teacher.objects.filter(user_id__in=teacher_user_ids)
                    .order_by('full_name')
                    .values_list('full_name', flat=True)
                )
        teacher_display = '، '.join(dict.fromkeys(teacher_names)) if teacher_names else 'غير محدد'

        reference_date = selected_end
        monthly_start, monthly_end = _month_bounds(reference_date)
        monthly_end = min(monthly_end, reference_date)

        attendance_as_of_reference = [
            attendance for attendance in all_attendance
            if attendance.session.date <= reference_date
        ]
        points_as_of_reference = [
            transaction for transaction in all_points
            if transaction.date.date() <= reference_date
        ]
        memorization_as_of_reference = [
            record for record in all_memorization
            if record.date <= reference_date
        ]
        plans_as_of_reference = [
            plan for plan in all_plans
            if plan.start_date <= reference_date
        ]
        homeworks_as_of_reference = [
            homework for homework in all_homeworks
            if homework.assigned_date <= reference_date
        ]

        monthly_points_total = sum(
            item.value for item in points_as_of_reference
            if monthly_start <= item.date.date() <= monthly_end
        )
        monthly_verses_total = sum(
            record.verses_count for record in memorization_as_of_reference
            if monthly_start <= record.date <= monthly_end
        )

        overall_attendance = _attendance_summary_from_records(attendance_as_of_reference)
        current_points_total = sum(item.value for item in points_as_of_reference)

        latest_memorization = memorization_as_of_reference[0] if memorization_as_of_reference else None
        latest_evaluation = next(
            (record for record in memorization_as_of_reference if record.evaluation),
            None,
        )
        latest_homework = next(
            (homework for homework in homeworks_as_of_reference if not homework.evaluation_date),
            homeworks_as_of_reference[0] if homeworks_as_of_reference else None,
        )
        latest_point_transaction = points_as_of_reference[0] if points_as_of_reference else None
        attendance_on_reference = next(
            (attendance for attendance in all_attendance if attendance.session.date == reference_date),
            None,
        )
        current_session = next(
            (session for session in all_sessions if session.date == reference_date),
            None,
        )

        attendance_records = [
            attendance for attendance in all_attendance
            if report_range['start'] <= attendance.session.date <= report_range['end']
        ]
        point_transactions = [
            transaction for transaction in all_points
            if report_range['start'] <= transaction.date.date() <= report_range['end']
        ]
        memorization_records = [
            record for record in all_memorization
            if report_range['start'] <= record.date <= report_range['end']
        ]
        plan_rows = [
            plan for plan in all_plans
            if plan.start_date <= report_range['end'] and plan.end_date >= report_range['start']
        ]
        homework_rows = [
            homework for homework in all_homeworks
            if (
                report_range['start'] <= homework.assigned_date <= report_range['end']
                or (homework.evaluation_date and report_range['start'] <= homework.evaluation_date <= report_range['end'])
                or (homework.assigned_date < report_range['start'] and not homework.evaluation_date)
            )
        ]
        sessions_in_range = [
            session for session in all_sessions
            if report_range['start'] <= session.date <= report_range['end']
        ]

        current_plan = next(
            (
                plan for plan in all_plans
                if plan.start_date <= reference_date <= plan.end_date and not plan.is_completed
            ),
            None,
        )
        current_plan_progress = _build_plan_progress(current_plan, memorization_as_of_reference, reference_date)
        performance_trend = _build_general_performance_trend(
            reference_date,
            attendance_as_of_reference,
            points_as_of_reference,
            homeworks_as_of_reference,
        )
        memorization_trend = _build_memorization_trend(reference_date, memorization_as_of_reference)

        attendance_report = _attendance_summary_from_records(attendance_records)
        memorization_verses_total = sum(item.verses_count for item in memorization_records)
        point_total = sum(item.value for item in point_transactions)
        point_positive_total = sum(item.value for item in point_transactions if item.value > 0)
        point_negative_total = abs(sum(item.value for item in point_transactions if item.value < 0))
        latest_memorization_in_range = memorization_records[0] if memorization_records else None
        latest_evaluation_in_range = next((item for item in memorization_records if item.evaluation), None)
        pending_homeworks_as_of_end = [
            homework for homework in homeworks_as_of_reference
            if not homework.evaluation_date or homework.evaluation_date > report_range['end']
        ]
        completed_homeworks_in_report = [
            homework for homework in homework_rows
            if homework.evaluation_date and homework.evaluation_date <= report_range['end']
        ]
        partial_homeworks_in_report = [
            homework for homework in completed_homeworks_in_report
            if homework.evaluation == 'partial'
        ]
        not_completed_homeworks_in_report = [
            homework for homework in completed_homeworks_in_report
            if homework.evaluation == 'not_completed'
        ]
        fully_completed_homeworks_in_report = [
            homework for homework in completed_homeworks_in_report
            if homework.evaluation in {'excellent', 'completed'}
        ]
        homework_total_in_report = len(completed_homeworks_in_report) + len(pending_homeworks_as_of_end)
        homework_completion_percentage = (
            round((len(fully_completed_homeworks_in_report) / homework_total_in_report) * 100)
            if homework_total_in_report else 0
        )
        recitation_quality_counts = {
            'excellent': 0,
            'very_good': 0,
            'good': 0,
            'needs_followup': 0,
            'unrated': 0,
        }
        for record in memorization_records:
            if record.evaluation in recitation_quality_counts:
                recitation_quality_counts[record.evaluation] += 1
            else:
                recitation_quality_counts['unrated'] += 1
        recitation_average_score = _average_choice_score(
            memorization_records,
            value_getter=lambda item: item.evaluation,
            score_map=MEMORIZATION_EVALUATION_SCORE_MAP,
        )
        recitation_quality_label = 'لا يوجد تقييم'
        if recitation_average_score >= 3.5:
            recitation_quality_label = 'ممتاز'
        elif recitation_average_score >= 2.5:
            recitation_quality_label = 'جيد جداً'
        elif recitation_average_score >= 1.5:
            recitation_quality_label = 'جيد'
        elif recitation_average_score:
            recitation_quality_label = 'يحتاج متابعة'

        teacher_notes = _build_teacher_notes(
            attendance_records,
            homework_rows,
            plan_rows,
            sessions_in_range,
            report_range['start'],
            report_range['end'],
        )

        timeline_entries = _build_timeline(
            report_range['start'],
            report_range['end'],
            attendance_records,
            point_transactions,
            memorization_records,
            homework_rows,
            plan_rows,
            sessions_in_range,
        )

        chart_days = _day_list(report_range['start'], report_range['end'])
        day_labels = _day_labels(chart_days)
        memorization_daily = {
            day: 0 for day in chart_days
        }
        points_daily = {
            day: 0 for day in chart_days
        }
        homework_assigned_daily = {
            day: 0 for day in chart_days
        }
        homework_evaluated_daily = {
            day: 0 for day in chart_days
        }
        attendance_daily = {
            day: {'score': None, 'status': '', 'label': 'لا يوجد تسجيل'}
            for day in chart_days
        }

        for record in memorization_records:
            memorization_daily[record.date] += record.verses_count
        for transaction in point_transactions:
            points_daily[transaction.date.date()] += transaction.value
        for attendance in attendance_records:
            attendance_daily[attendance.session.date] = {
                'score': ATTENDANCE_SCORE_MAP.get(attendance.status, 0),
                'status': attendance.status,
                'label': _status_label(attendance.status),
            }
        for homework in homework_rows:
            if homework.assigned_date in homework_assigned_daily:
                homework_assigned_daily[homework.assigned_date] += 1
            if homework.evaluation_date and homework.evaluation_date in homework_evaluated_daily:
                homework_evaluated_daily[homework.evaluation_date] += 1

        memorization_values = []
        points_cumulative = []
        points_running = 0
        attendance_scores = []
        attendance_colors = []
        attendance_statuses = []
        for day in chart_days:
            points_running += points_daily[day]
            memorization_values.append(memorization_daily[day])
            points_cumulative.append(points_running)
            attendance_scores.append(attendance_daily[day]['score'])
            attendance_statuses.append(attendance_daily[day]['label'])
            attendance_colors.append({
                'present': '#4CAF50',
                'excused': '#FFC107',
                'absent': '#F44336',
                '': '#D0D7DE',
            }.get(attendance_daily[day]['status'], '#D0D7DE'))

        latest_candidates = [
            (student.created_at, 'تسجيل الطالب'),
            (all_points[0].date if all_points else None, 'النقاط'),
            (_date_to_noon(all_memorization[0].date) if all_memorization else None, 'التسميع'),
            (_date_to_noon(all_attendance[0].session.date) if all_attendance else None, 'الحضور'),
            (all_homeworks[0].updated_at if all_homeworks else None, 'الواجب'),
            (_date_to_noon(all_plans[0].start_date) if all_plans else None, 'الخطة'),
        ]
        last_updated_at, last_updated_source = _max_candidate(latest_candidates)
        last_updated_display = (
            timezone.localtime(last_updated_at).strftime('%Y-%m-%d %H:%M')
            if last_updated_at else 'لا توجد تحديثات حتى الآن'
        )

        needs_followup = (
            len(pending_homeworks_as_of_end) > 0
            or (attendance_report['total'] and attendance_report['percentage'] < 70)
            or (latest_evaluation_in_range and latest_evaluation_in_range.evaluation == 'needs_followup')
        )
        status_badge = 'يحتاج متابعة' if needs_followup else 'جيد'
        if not attendance_report['total'] and not homework_rows and not memorization_records and not point_transactions:
            status_badge = 'لا توجد بيانات كافية'

        insight_parts = []
        if attendance_report['total']:
            insight_parts.append(
                f'حضر الطالب {attendance_report["present"]} من {attendance_report["total"]} حصص'
            )
        if pending_homeworks_as_of_end:
            insight_parts.append(f'وهناك {len(pending_homeworks_as_of_end)} واجب يحتاج متابعة')
        elif homework_rows:
            insight_parts.append('ولا توجد واجبات معلقة')
        if latest_evaluation_in_range:
            insight_parts.append(f'وآخر تسميع تقييمه {latest_evaluation_in_range.get_evaluation_display()}')
        period_insight = '، '.join(insight_parts) + '.'
        if not insight_parts:
            period_insight = 'لا توجد بيانات كافية داخل هذه الفترة، وستظهر المؤشرات عند إدخال السجلات.'

        master_report = {
            'label': report_range['label'],
            'start': report_range['start'].isoformat(),
            'end': report_range['end'].isoformat(),
            'attendance': attendance_report,
            'memorization': {
                'records': len(memorization_records),
                'verses_total': memorization_verses_total,
                'latest_record_date': latest_memorization_in_range.date.isoformat() if latest_memorization_in_range else '',
                'latest_evaluation': latest_evaluation_in_range.get_evaluation_display() if latest_evaluation_in_range else 'لا يوجد تقييم',
                'quality_label': recitation_quality_label,
                'average_score': recitation_average_score,
            },
            'points': {
                'net_total': point_total,
                'positive_total': point_positive_total,
                'negative_total': point_negative_total,
                'count': len(point_transactions),
                'current_total': current_points_total,
            },
            'homework': {
                'assigned_count': sum(1 for item in homework_rows if report_range['start'] <= item.assigned_date <= report_range['end']),
                'evaluated_count': len(completed_homeworks_in_report),
                'completed_count': len(fully_completed_homeworks_in_report),
                'partial_count': len(partial_homeworks_in_report),
                'not_completed_count': len(not_completed_homeworks_in_report),
                'pending_count': len(pending_homeworks_as_of_end),
                'total_count': homework_total_in_report,
                'completion_percentage': homework_completion_percentage,
            },
            'plan': {
                'status_label': current_plan_progress['status_label'],
                'expected_percent': current_plan_progress['expected_percent'],
                'actual_percent': current_plan_progress['actual_percent'],
                'total_pages': current_plan_progress['total_pages'],
                'completed_pages': current_plan_progress['completed_pages'],
                'remaining_pages': current_plan_progress['remaining_pages'],
                'required_pages_per_day': current_plan_progress['required_pages_per_day'],
                'target': current_plan_progress['target'] or 'لا توجد خطة',
            },
            'teacher_notes_count': len(teacher_notes),
        }

        summary = {
            'student_name': student.name,
            'halaqa_name': halaqa.name if halaqa else 'غير مسجل في حلقة',
            'category': _infer_category(student),
            'teacher': teacher_display,
            'last_updated_display': last_updated_display,
            'last_updated_source': last_updated_source or 'النظام',
            'reference_date': reference_date.isoformat(),
            'status_badge': status_badge,
            'period_insight': period_insight,
            'attendance_percentage': overall_attendance['percentage'],
            'attendance_reference': {
                'date': reference_date.isoformat(),
                'status_label': attendance_on_reference.get_status_display() if attendance_on_reference else 'لا يوجد تسجيل',
                'status_code': attendance_on_reference.status if attendance_on_reference else '',
                'note': attendance_on_reference.notes if attendance_on_reference and attendance_on_reference.notes else '',
                'source_label': _attendance_source_label(attendance_on_reference),
                'session_note': current_session.notes if current_session and current_session.notes else '',
                'present': overall_attendance['present'],
                'absent': overall_attendance['absent'],
                'excused': overall_attendance['excused'],
                'total': overall_attendance['total'],
            },
            'points': {
                'current_total': current_points_total,
                'monthly_total': monthly_points_total,
                'latest_value': latest_point_transaction.value if latest_point_transaction else 0,
                'latest_reason': latest_point_transaction.reason if latest_point_transaction else '',
                'latest_date': (
                    timezone.localtime(latest_point_transaction.date).strftime('%Y-%m-%d %H:%M')
                    if latest_point_transaction else ''
                ),
            },
            'monthly_memorized_verses': monthly_verses_total,
            'latest_recitation': (
                {
                    'surah': latest_memorization.recitation_title,
                    'range': latest_memorization.recitation_range,
                    'date': latest_memorization.date.isoformat(),
                    'verses_count': latest_memorization.verses_count,
                    'source': latest_memorization.get_recitation_type_display(),
                    'evaluation_label': (
                        latest_memorization.get_evaluation_display()
                        if latest_memorization.evaluation else 'بدون تقييم'
                    ),
                }
                if latest_memorization else
                {
                    'surah': '',
                    'range': '',
                    'date': '',
                    'verses_count': 0,
                    'evaluation_label': 'لا يوجد تسميع مسجل حتى الآن',
                }
            ),
            'performance_trend': performance_trend,
            'memorization_trend': memorization_trend,
            'homework': _build_homework_snapshot(latest_homework, reference_date),
            'plan': {
                'status': current_plan_progress['status'],
                'status_label': current_plan_progress['status_label'],
                'badge_class': current_plan_progress['badge_class'],
                'target': current_plan_progress['target'],
                'date_range': current_plan_progress['date_range'],
                'expected_percent': current_plan_progress['expected_percent'],
                'actual_percent': current_plan_progress['actual_percent'],
                'total_pages': current_plan_progress['total_pages'],
                'completed_pages': current_plan_progress['completed_pages'],
                'remaining_pages': current_plan_progress['remaining_pages'],
                'remaining_days': current_plan_progress['remaining_days'],
                'required_pages_per_day': current_plan_progress['required_pages_per_day'],
                'notes': current_plan_progress['notes'],
            },
        }

        return render(request, 'students/students_data.html', {
            'student': student,
            'halaqa': halaqa,
            'parent_name': student.parent.first_name if student.parent else '',
            'parent_phone': student.parent_phone,
            'teacher_display': teacher_display,
            'category_label': _infer_category(student),
            'summary': summary,
            'report_range': report_range,
            'master_report': master_report,
            'timeline_entries': timeline_entries,
            'attendance_rows': attendance_records,
            'points_rows': point_transactions,
            'memorization_rows': memorization_records,
            'homework_rows': homework_rows,
            'plan_rows': plan_rows,
            'teacher_notes': teacher_notes,
            'attendance_chart': {
                'labels': day_labels,
                'values': attendance_scores,
                'colors': attendance_colors,
                'statuses': attendance_statuses,
            },
            'memorization_chart': {
                'labels': day_labels,
                'values': memorization_values,
            },
            'points_chart': {
                'labels': day_labels,
                'values': points_cumulative,
            },
            'homework_chart': {
                'labels': day_labels,
                'assigned': [homework_assigned_daily[day] for day in chart_days],
                'evaluated': [homework_evaluated_daily[day] for day in chart_days],
            },
            'plan_chart': {
                'labels': current_plan_progress['labels'],
                'expected': current_plan_progress['expected_values'],
                'actual': current_plan_progress['actual_values'],
            },
            'plan_progress': current_plan_progress,
            'homework_status_chart': {
                'labels': ['منجز', 'جزئي', 'غير منجز', 'بانتظار التقييم'],
                'values': [
                    len(fully_completed_homeworks_in_report),
                    len(partial_homeworks_in_report),
                    len(not_completed_homeworks_in_report),
                    len(pending_homeworks_as_of_end),
                ],
            },
            'recitation_quality_chart': {
                'labels': ['ممتاز', 'جيد جداً', 'جيد', 'يحتاج متابعة', 'بدون تقييم'],
                'values': [
                    recitation_quality_counts['excellent'],
                    recitation_quality_counts['very_good'],
                    recitation_quality_counts['good'],
                    recitation_quality_counts['needs_followup'],
                    recitation_quality_counts['unrated'],
                ],
            },
        })

    @action(detail=False, methods=['get'], url_path='dashboard', permission_classes=[AllowAny])
    def dashboard(self, request):
        halaqas = Halaqa.objects.filter(is_active=True).annotate(
            member_count=Count('members', filter=Q(members__is_active=True))
        )
        return render(request, 'students/dashboard.html', {
            'halaqas': halaqas
        })


class MemorizationRecordViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = MemorizationRecord.objects.all()
    serializer_class = MemorizationRecordSerializer
    permission_classes = [AllowAny]
    lookup_field = 'id'

    def get_queryset(self):
        student_id = self.request.query_params.get('student_id')
        if student_id:
            return self.queryset.filter(student__id=student_id)
        return self.queryset.all()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user if getattr(request.user, 'is_authenticated', False) else None
        save_kwargs = {'created_by': user}
        if serializer.validated_data.get('is_approved') and user and not serializer.validated_data.get('approved_by'):
            save_kwargs['approved_by'] = user
        memorization_record = serializer.save(**save_kwargs)
        return Response({
            "msg": "تم إنشاء سجل الحفظ بنجاح",
            "record_id": memorization_record.id,
            "id": memorization_record.id,
            "verses_count": memorization_record.verses_count,
        }, status=status.HTTP_201_CREATED)
