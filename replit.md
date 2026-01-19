# MA Tool - 大学向けマーケティングオートメーションツール

## Overview
This project is an MVP (Minimum Viable Product) of a Marketing Automation (MA) tool designed for universities. Its primary purpose is to automate the delivery of grade-optimized emails to high school students and current students based on their graduation year and event triggers, using university-owned CSV data. The tool aims to streamline communication with prospective and current students, enhancing engagement and recruitment efforts. Key capabilities include automated email delivery, robust data handling with CSV import/normalization, template management with an approval workflow, email tracking, and integration with LINE Messaging API.

## User Preferences
I prefer iterative development with clear, modular components. Please ensure code is well-documented and follows best practices for maintainability and scalability. I value detailed explanations of complex features or architectural decisions. Do not make changes to the existing project structure without explicit approval. When implementing new features, prioritize security, especially concerning personal data and email misdelivery prevention.

## System Architecture
The MA tool is built upon a modern web stack using FastAPI for the API, PostgreSQL for the database, SQLAlchemy 2.x with Alembic for ORM and migrations, APScheduler for background tasks, and Jinja2 for server-side rendered UI templates.

**UI/UX Decisions:**
- **Admin UI (Bootstrap 5 + HTMX):** Comprehensive web-based admin interface with session authentication at `/ui/`.
  - **Session Authentication:** Email-based login requiring pre-registered users in the database. Uses `SESSION_SECRET_KEY` environment variable.
  - **Leads Management:** Search, filter by graduation year, view lead details, and manage LINE identity links at `/ui/leads`.
  - **LINE Identity Management:** View all LINE identities, link/unlink leads, with full audit logging at `/ui/line-identities`.
  - **Template Management:** Create, edit, clone templates with LINE support (Flex Message JSON), submit for approval, approve/reject workflows, and test send functionality (dev/staging only) at `/ui/templates`.
  - **Scenario Management:** Create and manage scenarios with target preview showing eligible leads count at `/ui/scenarios`. Supports both lead-creation-based and event-date-based scheduling.
  - **Event Management:** Create and manage calendar events (Open Campus, briefings, etc.) with participant registration at `/ui/events`. Events can be linked to scenarios for event-date-based email scheduling (e.g., send reminder 7 days before event).
  - **Send Logs:** View all message delivery logs with multi-filter support (status, channel, scenario, graduation year) at `/ui/send-logs`.
  - **Environment Banner:** Shows current environment (DEV/STAGING/PRODUCTION) for safety awareness.
  - **Toast Notifications:** Real-time feedback via HTMX triggers.
- **Legacy Dashboard UI:** Analytical insights into email campaigns with daily, graduation year, and scenario-specific statistics.
- **CSV Import Workflow:** Implements a two-step preview-and-confirm process to prevent data import errors, supported by automatic column mapping and value normalization for various Japanese and English data formats.
  - Supports new CSV format: 個人ID, 漢字氏名, 高校正式名称, 卒年, メールアドレス1, メールアドレス2
  - Email fallback: Uses メールアドレス1 primarily, falls back to メールアドレス2 if empty
  - Consent defaults to True (university-collected data assumption)
  - External ID (個人ID) stored for tracking

**Technical Implementations:**
- **Personal Data Protection:** Includes features for consent management, unsubscribe functionality, comprehensive audit logging of critical operations, and role-based access control.
- **Email Misdelivery Prevention:** In `dev`/`staging` environments, all emails are redirected to `MAIL_REDIRECT_TO` address.
- **LINE Misdelivery Prevention:** In `dev`/`staging` environments, LINE messages are redirected to `LINE_TEST_USER_ID`.
- **Template Variable System:** Supports dynamic content substitution:
  - `{{ lead_name }}`, `{{ lead_email }}`, `{{ lead_school_name }}`, `{{ lead_graduation_year }}`
  - `{{ unsubscribe_url }}` - Auto-inserted if not present in template
  - `{{ line_friend_add_url }}` - For directing users to university's official LINE account
- **Graduation Year Estimation:** Automatically infers graduation year from `grade_label` in CSV data if `graduation_year` is missing.
- **Messaging Service Abstraction:** Decouples message sending logic from specific providers (Email via SendGrid, LINE via Messaging API), supporting multi-channel delivery.
- **Scenario Execution Engine:** APScheduler runs every 5 minutes to evaluate scenarios, identify eligible leads based on consent, unsubscribe status, approved templates, graduation year rules (e.g., `within_months`), frequency limits, and prevents duplicate sends. Supports two base date types:
  - `lead_created_at`: Traditional trigger-based scheduling (send X days after lead registration)
  - `event_date`: Event-based scheduling (send X days before/after calendar event date for registered participants)
- **Email Tracking:** Implements 1x1 pixel tracking for email opens.
- **Template Approval Workflow:** Templates transition through `draft`, `pending`, `approved`, and `rejected` states, ensuring content quality and preventing unauthorized modifications to approved templates.
- **Role-Based Access Control (RBAC):** Differentiates user permissions (admin, editor, approver, viewer) for various operations on templates and other features.
- **Sending Time Window:** Emails are scheduled to be sent between 9:00 and 20:00 JST, with rollovers for messages scheduled outside this window.
- **Rate Limiting:** Configurable email sending rate limit (default 60 emails/minute) to manage load and comply with ESP policies.
- **LINE Webhook Integration:** Handles Follow/Unfollow/Message events with mandatory HMAC-SHA256 signature verification. Supports secure user linking via signed tokens (LINK: command with 1-hour expiration).

**System Design Choices:**
- **Modular Project Structure:** Organized into `api`, `models`, `schemas`, and `services` to enhance maintainability and separation of concerns.
- **Robust CSV Handling:** Supports automatic character encoding detection and detailed validation for imported data, including hard (error) and soft (warning) mandatory fields.
- **Unique Constraint for Sends:** `send_logs` table enforces uniqueness on `lead_id`, `scenario_id`, and `event_id` (or `calendar_event_id` for event-based scenarios) to prevent duplicate emails for the same trigger.
- **Event Types:** Supports multiple event types: Open Campus (oc), briefings, interviews, tours, and other custom types.

## Environment Variables
- `APP_ENV` - Environment: dev, staging, or prod
- `DATABASE_URL` - PostgreSQL connection string
- `SENDGRID_API_KEY` - SendGrid API key for email delivery
- `MAIL_FROM` - Sender email address (university domain)
- `MAIL_REPLY_TO` - Reply-to address for inquiries
- `MAIL_REDIRECT_TO` - Test recipient for dev/staging (required in non-prod)
- `MAIL_ALLOWLIST` - Optional domain allowlist
- `LINE_FRIEND_ADD_URL` - University's official LINE friend add URL
- `UNSUBSCRIBE_SECRET` - Secret for signed unsubscribe tokens
- `SESSION_SECRET_KEY` - Session encryption key

## External Dependencies
- **PostgreSQL:** Primary database for persistent storage.
- **SendGrid:** Email Service Provider (ESP) for sending emails. (Configured via `SENDGRID_API_KEY`)
- **LINE Messaging API:** For sending LINE messages and handling webhooks. (Configured via `LINE_CHANNEL_ACCESS_TOKEN`, `LINE_CHANNEL_SECRET`)
- **uvicorn:** ASGI server for running the FastAPI application.
- **alembic:** Database migration tool.
- **APScheduler:** In-process task scheduler for background jobs like scenario execution.
- **Jinja2:** Templating engine for server-side rendered HTML UI.
- **Pydantic:** Data validation and settings management.
- **SQLAlchemy:** Object-Relational Mapper (ORM) for database interaction.