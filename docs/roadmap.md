# Roadmap

## Phase 2: opt-in auto-booking

Book the earliest qualifying slot automatically, only when you switch it on.

**Planned design:**

- **Connect account (options flow).** Sign in to EasyVisit (Sonic Healthcare ID) in your browser, then paste back the redirected URL. This is an OAuth code + PKCE exchange. The integration stores the access and refresh tokens and refreshes them automatically. If the refresh token stops working, Home Assistant asks you to sign in again.
- **Per doctor:**
  - an **Auto-book** switch (default off)
  - a **Patient** select: you or a family member on your EasyVisit account
- **When a new qualifying slot appears and Auto-book is on:**
  1. Lock the earliest slot. If it's taken, try the next one, up to 3 times.
  2. Check the patient has no other booking that day. If they do, notify instead of booking.
  3. Book, and notify with the details. Some doctors need the practice to confirm web bookings.
  4. **Turn Auto-book off**, so there is never a second booking.
- Existing appointments are never cancelled.

**Open questions:**
- What the `Token` field on the booking request needs for signed-in users.
- How long the web client's refresh tokens last. If they're short, the mobile app's client may be needed.

See the booking section of [API.md](../API.md).

## Ideas

- Time-of-day and weekday filters (e.g. only mornings, or never Fridays)
- Quiet hours for notifications
- Actionable notification buttons (Book / Snooze)
