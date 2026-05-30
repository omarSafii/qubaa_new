# Quba Quran Halaqa Management System

## Overview

Quba Quran Halaqa Management System is a Django-based management platform for Quran halaqas at Quba Institute for Quran Memorization.

It is designed to manage:

- students
- parents
- teachers
- supervisors
- halaqas
- attendance
- homework
- recitation and memorization records
- points
- plans
- reports
- parent progress pages

The main application lives in the `backend/` directory. A small `frontend/` directory still exists in the repository and appears to contain older static prototype files.

## Main User Roles

### Admin

Admins manage the platform at a high level. In practice this includes Django admin access, master dashboard access, user/data oversight, and broad visibility across halaqas, attendance, homework, reports, and related records.

### Teacher

Teachers work inside their halaqa dashboard and halaqa detail pages. They can register or manage students in context, record attendance, assign homework, evaluate recitation, award or deduct points, create plans, and review student progress for their assigned halaqa.

### Supervisor

Supervisors use a dedicated supervisor workflow to record attendance across halaqas. The workflow is organized as category selection, then halaqa selection, then student attendance entry.

### Parent/Student

Parents and students can use a private progress page powered by an access token. That page provides a read-only view of attendance, homework, recitation, points, plans, notes, and summary/report data for a student.

## Main Features

- Student registration.
- Teacher halaqa dashboard.
- Expandable, mobile-friendly student rows.
- Student actions remain hidden until the row is expanded.
- Attendance recording.
- Teacher/supervisor attendance conflict prevention.
- Supervisor dashboard and attendance workflow.
- Supervisor flow: category selection -> halaqa selection -> student attendance.
- Homework and recitation workflow centered around homework.
- Blocking new active homework when unfinished homework already exists.
- Suggested expected recitation dates.
- Extra/free recitation support.
- Parent/student private progress page by access token.
- Redesigned parent page with summary/report tabs, charts, cards, attendance, homework, recitation, points, plans, and notes.

## Recent Major Updates

### 1. Supervisor attendance feature

- Added the supervisor role.
- Added a supervisor dashboard at `/halaqas/supervisor/`.
- Reused the existing `Attendance` and `Session` system.
- Added attendance recorder metadata: `recorded_by` and `recorded_by_role`.
- Supervisor-recorded attendance is visible to teachers and on parent-facing progress pages.

### 2. Attendance conflict prevention

- A teacher cannot overwrite attendance already recorded by a supervisor.
- A supervisor cannot overwrite attendance already recorded by a teacher.
- Locked attendance is shown visually in the UI.
- The backend enforces the overwrite rules, not only the frontend.

### 3. Teacher halaqa page UI refinement

- Student rows are expandable.
- Rows are compact and mobile-friendly.
- Student actions stay hidden until the teacher expands a student row.
- Existing actions and modal workflows are preserved.

### 4. Supervisor dashboard refinement

- Supervisors first select a category.
- Then they select a halaqa.
- Then they record attendance for that halaqa's students.
- This replaces a long all-halaqas-at-once layout.

### 5. Homework and recitation refactor

- The standalone primary "record memorization/recitation" action was removed from the main workflow.
- Homework is now the primary teacher workflow.
- Homework supports pages, surah, verse range, notes, and expected recitation date.
- Expected recitation date is suggested as:
  - Saturday -> next Tuesday
  - Tuesday -> next Saturday
  - otherwise -> nearest Saturday or Tuesday
- A student cannot receive new active homework while unfinished homework exists.
- Homework evaluation creates or updates linked memorization records.
- Extra/free recitation is still supported.
- Recitation records are still saved for analytics and reports.

### 6. Parent/student progress page redesign

- The page was rebuilt into two tabs: `الملخص` and `التقرير`.
- The summary tab presents mobile-friendly cards and charts.
- The report tab keeps the detailed report view in a cleaner layout.
- The access-token-based sharing logic stayed unchanged.

## Project Structure

- `backend/` - main Django project root.
- `backend/accounts/` - profile, authentication-related views, permissions, and account templates.
- `backend/students/` - student models, memorization records, student dashboard/progress pages, and student APIs.
- `backend/halaqas/` - halaqa management, teacher/supervisor flows, attendance, homework, plans, points, and admin dashboards.
- `backend/qubaa_project/` - Django project settings, URL configuration, WSGI/ASGI entry points.
- `backend/requirements.txt` - Python dependencies.
- `backend/.env.example` - example environment configuration.
- `backend/gunicorn.conf.py` - Gunicorn runtime configuration.
- `frontend/` - legacy/static prototype HTML files that still exist in the repository.

## Important URLs

Actual access depends on authentication state and role permissions.

- `/admin/` - Django admin.
- `/accounts/login_page/` - HTML login page.
- `/students/dashboard/` - student-related dashboard endpoint.
- `/students/students_data/<access_token>/` - private parent/student progress page.
- `/halaqas/halaqa/<id>/` - halaqa detail page.
- `/halaqas/supervisor/` - supervisor dashboard.
- `/halaqas/admin-dashboard/` - admin dashboard.

Useful API/auth routes also exist, including:

- `/api/token/`
- `/api/token/refresh/`
- `/api/users/me/`

## Main Models

- `Profile` - stores the main application role for each user.
- `Student` - student profile, parent linkage, halaqa/category snapshot, and access token.
- `MemorizationRecord` - recitation or memorization entries, including homework-linked evaluations.
- `Category` - official halaqa/student category definitions.
- `Teacher` - teacher identity and current halaqa assignment.
- `Halaqa` - halaqa container with teachers, join code, and share link.
- `TeacherAssignment` - explicit teacher-to-halaqa assignment history.
- `HalaqaMembership` - active/inactive student membership history per halaqa.
- `Session` - dated halaqa session used by attendance flows.
- `Attendance` - per-student attendance status for a session, including recorder metadata.
- `Homework` - assigned and evaluated homework, expected recitation date, and notes.
- `PointTransaction` - point additions/deductions with running balance snapshots.
- `Plan` - time-boxed student improvement or study plans.

## Setup Instructions

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd qubaa
```

### 2. Create a virtual environment

```bash
cd backend
python -m venv env
```

### 3. Activate the virtual environment

Windows:

```bash
env\Scripts\activate
```

Linux/macOS:

```bash
source env/bin/activate
```

### 4. Install requirements

```bash
pip install -r requirements.txt
```

### 5. Configure environment variables

Copy values from `backend/.env.example` into your local environment or your preferred secrets management approach.

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create a superuser

```bash
python manage.py createsuperuser
```

### 8. Run the development server

```bash
python manage.py runserver
```

## Environment Variables

The following settings are the main ones to know for local development and deployment:

| Variable | Purpose | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key | Required in production. |
| `DJANGO_DEBUG` | Enables/disables debug mode | Defaults to local-friendly behavior when `DATABASE_URL` is not set. |
| `DATABASE_URL` | Database connection string | Production expects PostgreSQL-style URLs. Local development falls back to SQLite when omitted. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated trusted origins | Important for hosted deployments and custom domains. |
| `DJANGO_CORS_ALLOWED_ORIGINS` | Comma-separated allowed frontend origins | Useful when frontend and backend are on different origins. |
| `DJANGO_SECURE_SSL_REDIRECT` | Force HTTPS redirects | Usually enabled in production. |
| `DJANGO_STATIC_ROOT` | Static files output path | Used by `collectstatic`. |
| `DJANGO_MEDIA_ROOT` | Media storage path | Override if needed in deployment. |
| `DJANGO_DB_CONN_MAX_AGE` | Database connection reuse | Supported by settings and shown in `.env.example`. |
| `WEB_CONCURRENCY` | Gunicorn worker count | Used by `backend/gunicorn.conf.py`. |
| `GUNICORN_TIMEOUT` | Gunicorn timeout | Used by `backend/gunicorn.conf.py`. |

Additional note:

- `DJANGO_ALLOWED_HOSTS` is documented in `backend/.env.example`, but the current `backend/qubaa_project/settings.py` does not read that variable. `ALLOWED_HOSTS` is currently hard-coded in settings, so this should be confirmed before relying on the variable in deployment.

## Migrations

After pulling new updates, always apply migrations:

```bash
python manage.py migrate
```

Recent migration areas include:

- supervisor role support
- attendance recorder metadata
- homework expected recitation details
- memorization record homework/page links

## Running Tests

```bash
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test
```

## Deployment Notes

- The project has been deployed on Render.
- Production requires at least `DATABASE_URL` and `DJANGO_SECRET_KEY`.
- Static files are served with WhiteNoise.
- Gunicorn configuration exists in `backend/gunicorn.conf.py`.
- `collectstatic` may be required during deployment.
- When new migration files are added, migrations must be applied after deployment.
- If a future custom domain or paid hosting setup is introduced, confirm `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` again.
- There is no `render.yaml` or `Procfile` in the repository at the moment, so deployment commands may be configured directly in the hosting dashboard.

## Manual Testing Checklist

- [ ] Login as admin.
- [ ] Login as teacher.
- [ ] Open the teacher halaqa page.
- [ ] Expand a student row.
- [ ] Record attendance, homework, points, and a plan.
- [ ] Confirm attendance conflict prevention between teacher and supervisor.
- [ ] Login as supervisor.
- [ ] Open the supervisor dashboard.
- [ ] Select a category, then a halaqa, then record attendance.
- [ ] Open the parent access-token page.
- [ ] Check the summary and report tabs.
- [ ] Test the key pages at mobile width.

## Security Notes

- Protect sensitive dashboards and APIs behind proper authentication and authorization.
- Keep `SECRET_KEY`, `DATABASE_URL`, and other secrets out of Git.
- Do not commit real production data.
- Review fixture/sample data before sharing the repository.
- Parent progress links rely on private access tokens and should be treated as sensitive.

## Known Follow-up Improvements

- Improve and standardize the authentication flow.
- Review and tighten API permissions.
- Improve the README further once final deployment settings are confirmed.
- Clean old prototype frontend files if they are no longer needed.
- Add more production deployment documentation.
- Add more tests for homework and supervisor workflows.
