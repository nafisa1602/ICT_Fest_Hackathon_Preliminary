# Bug Fixes Report — CoWork Booking API

This document details all bugs identified and resolved in the CoWork Booking API during the Agentic AI Hackathon.

---

## 1. Datetime Parsing & Timezone Normalization
* **Location:** `app/timeutils.py:13`
* **Issue:** Localized input datetimes with timezone offsets had their offsets stripped (via `replace(tzinfo=None)`) without converting the actual hour/minute values to UTC first, resulting in incorrect stored times.
* **Fix:** Normalized datetime objects to UTC using `.astimezone(timezone.utc)` prior to stripping timezone information for naive database storage.

---

## 2. Past Booking Validation & Grace Period
* **Location:** `app/routers/bookings.py:86`
* **Issue:** Allowed past bookings up to 5 minutes ago (grace window), which violates Business Rule 2 (strict future requirement).
* **Fix:** Enforced a strict validation: if `start <= now`, the request is rejected with a `400 INVALID_BOOKING_WINDOW` error.

---

## 3. Duration Range Bounds & Whole Hour Increments
* **Location:** `app/routers/bookings.py:89-93`
* **Issue:** The API allowed bookings with a duration under 1 hour or non-whole hours, and did not reject requests where `end_time <= start_time`.
* **Fix:** Enforced `end_time > start_time` checks, checked that duration in hours is a whole integer (`duration_hours == int(duration_hours)`), and validated that it is between `1` and `8` hours inclusive.

---

## 4. Back-to-Back Booking Overlap Conflict Checks
* **Location:** `app/routers/bookings.py:50`
* **Issue:** Overlap check logic used inclusive operators (`<=`), meaning back-to-back bookings (where one ends exactly when another starts) were incorrectly flagged as conflicts.
* **Fix:** Replaced inclusive operators with strict inequalities: `existing.start < new.end and new.start < existing.end`.

---

## 5. Member Quota Scope Enforcement
* **Location:** `app/routers/bookings.py:103`
* **Issue:** Quota limits (maximum of 3 confirmed bookings in `[now, now + 24h]`) were incorrectly applied to administrators, restricting room setup.
* **Fix:** Scoped the quota validation check to run only when the calling user's role is `"member"`.

---

## 6. Booking Listing Pagination, Sorting, and Limits
* **Location:** `app/routers/bookings.py:137-139`
* **Issue:** Pagination calculations used an incorrect offset formula (`page * limit`), sorted results in descending order, and ignored the user-specified limit parameter.
* **Fix:** Replaced the offset with `(page - 1) * limit`, changed the sort order to ascending by `start_time` (then `id` as tie-breaker), and respected the `limit` query parameter.

---

## 7. Non-Admin Booking Detail Visibility Leak
* **Location:** `app/routers/bookings.py:159` & `app/routers/bookings.py:166`
* **Issue:** Members could fetch details for other users' bookings within the same organization. Additionally, the single-booking response incorrectly overwrote the `start_time` field with the booking creation timestamp.
* **Fix:** Implemented an ownership check preventing members from reading bookings not belonging to them (raising `404 BOOKING_NOT_FOUND`), and removed the line overwriting `start_time`.

---

## 8. Cancellation Refund Policy Brackets
* **Location:** `app/routers/bookings.py:200-206`
* **Issue:** Cancellation notice periods under 24 hours returned a 50% refund (should be 0%), and exactly 48 hours returned 50% (should be 100%).
* **Fix:** Refactored notice tier checks: `notice >= 48 hours` yields 100% refund, `24 <= notice < 48` yields 50%, and `< 24` yields 0%.

---

## 9. Cents Precision Rounding & Atomic Transactions
* **Location:** `app/services/refunds.py:14-25` & `app/routers/bookings.py:208`
* **Issue:** Python's default bankers' rounding caused incorrect cent allocations (e.g. `500.5` rounded down to `500` instead of up to `501`). Furthermore, commits were made inside `log_refund` separately from `cancel_booking`, risking half-failed transactions.
* **Fix:** Utilized `int(cents * ratio + 0.5)` for standard round-half-up integer rounding and replaced `db.commit()` inside `log_refund` with `db.flush()` so that cancellations and refund logs commit atomically.

---

## 10. Database Constraints
* **Location:** `app/models.py:55` and `app/models.py:66`
* **Issue:** Database models lacked uniqueness constraints on `Booking.reference_code` and `RefundLog.booking_id`, making them vulnerable to duplicate writes.
* **Fix:** Configured `unique=True` on both model fields.

---

## 11. Cache Invalidation
* **Location:** `app/routers/bookings.py:121` & `app/routers/bookings.py:217`
* **Issue:** Creating a booking only invalidated availability cache, and cancelling only invalidated report cache, leading to stale reports and availability data.
* **Fix:** Ensured both availability and report caches are invalidated in both creation and cancellation flows.

---

## 12. Persistent Room Statistics
* **Location:** `app/routers/rooms.py:110`
* **Issue:** Stats endpoints fetched data from an in-memory dictionary that was reset on server restarts.
* **Fix:** Re-routed stats generation to fetch counts and revenue directly from active database bookings.

---

## 13. JWT Access Token Expiry Lifetimes
* **Location:** `app/auth.py:50`
* **Issue:** Access tokens expired after 15 hours instead of 15 minutes due to an extra `* 60` multiplier.
* **Fix:** Removed the `* 60` multiplier from the expiration delta calculation.

---

## 14. JWT Revocation Verification
* **Location:** `app/auth.py:86` & `app/auth.py:97`
* **Issue:** Logout blacklisted the token ID (`jti`) but verification looked up the user ID (`sub`), allowing blacklisted access tokens to remain active.
* **Fix:** Updated the verification path to check the `jti` claim against the blacklist.

---

## 15. Single-Use Refresh Token Enforcement
* **Location:** `app/routers/auth.py:82`
* **Issue:** Refresh tokens were reusable, violating safety standards.
* **Fix:** Added a thread-safe `used_refresh_jtis` set that stores used refresh token `jti` claims, rejecting token reuse with a `401` error.

---

## 16. Duplicate Username Registrations
* **Location:** `app/routers/auth.py:37`
* **Issue:** Registering an existing username under the same organization returned the existing user object with a `200` status instead of rejecting the registration.
* **Fix:** Threw a `409 USERNAME_TAKEN` AppError if the username is already registered in that organization.

---

## 17. Concurrency Safety Locks
* **Location:** `app/services/ratelimit.py`, `app/services/stats.py`, `app/services/reference.py`, and `app/routers/bookings.py`
* **Issue:** Concurrent operations on rate limiters, booking counters, reference generators, and booking creation/cancellation databases created race conditions.
* **Fix:** Synchronized concurrent request paths by introducing `threading.Lock` wrappers.

---

## 18. Liveness Deadlocks
* **Location:** `app/services/notifications.py:24-34`
* **Issue:** `notify_created` nested `_email_lock` then `_audit_lock`, while `notify_cancelled` nested them in the opposite order, leading to thread deadlocks.
* **Fix:** Refactored notification locks to be acquired sequentially, eliminating deadlock conditions.

---

## 19. Admin Export Scoping Checks
* **Location:** `app/services/export.py:50` & `app/routers/admin.py:67-72`
* **Issue:** Exporting room bookings with `include_all` bypassed organization boundaries, leaking other organizations' bookings.
* **Fix:** Added ownership validation on the target `room_id`, raising a `404 ROOM_NOT_FOUND` error if the room belongs to a different organization.

---

## 20. Redis Dependency & Test suite liveness
* **Location:** `app/config.py`, `requirements.txt`, and `tests/conftest.py`
* **Issue:** The addition of Redis for token revocation lacked package requirements, configuration URL settings, and caused unit tests to fail due to the absence of a local Redis service.
* **Fix:** Added `redis` to `requirements.txt`, configured `REDIS_URL` in `config.py`, and created a mock Redis fixture in `tests/conftest.py` so the test suite can run successfully without an active Redis instance.
