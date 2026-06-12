from django.db.models import Q

from .models import Halaqa, Teacher, TeacherAssignment


ADMIN_ROLES = {"admin"}
SUPERVISOR_ROLES = {"supervisor"}


def role_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return ""
    if getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return "admin"
    profile = getattr(user, "profile", None)
    return getattr(profile, "role", "") or ""


def is_admin_user(user):
    return role_for_user(user) in ADMIN_ROLES


def is_supervisor_user(user):
    return role_for_user(user) in SUPERVISOR_ROLES


def teacher_for_user(user):
    if not user or not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "teacher", None)


def assigned_halaqas_for_teacher(teacher):
    if not teacher:
        return Halaqa.objects.none()

    active_assignment_halaqa_ids = TeacherAssignment.objects.filter(
        teacher=teacher,
        is_active=True,
        halaqa__is_active=True,
    ).values_list("halaqa_id", flat=True)

    return (
        Halaqa.objects.filter(
            Q(teachers=teacher) | Q(pk__in=active_assignment_halaqa_ids),
            is_active=True,
        )
        .distinct()
        .order_by("name")
    )


def assigned_halaqas_for_user(user):
    return assigned_halaqas_for_teacher(teacher_for_user(user))


def user_can_access_halaqa(user, halaqa):
    role = role_for_user(user)
    if role in ADMIN_ROLES or getattr(user, "is_superuser", False) or getattr(user, "is_staff", False):
        return True
    if role in SUPERVISOR_ROLES:
        return True

    teacher = teacher_for_user(user)
    if not teacher:
        return False

    return assigned_halaqas_for_teacher(teacher).filter(pk=halaqa.pk).exists()
