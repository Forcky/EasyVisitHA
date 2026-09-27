# EasyVisit API notes

Reverse-engineered from the web booking app (`https://web.easyvisit.com.au`, an Angular SPA, `main.<hash>.js`) in September 2026 and confirmed with live calls. Nothing here is documented by EasyVisit / Sonic Healthcare.

## Configuration

`GET https://web.easyvisit.com.au/assets/config/config.json` (public):

| key | value |
|---|---|
| `apiUrl` | `https://api.easyvisit.com.au` |
| `openid_connect_url` | `https://identity.apps.sonichealthcare.com/` (Gluu oxauth) |
| `client_id` | `eddb4e22-b4f9-479e-b079-e80b6ad2730e` (public PKCE client) |
| `redirect_uri` | `https://web.easyvisit.com.au/login` |
| `scope` | `openid email profile permission mobile_phone offline_access` |
| `appDeepLinkUrl` | `com.sonichealthcare.easyvisit:/` (the mobile app's redirect) |

OIDC endpoints: `/oxauth/restv1/authorize`, `/oxauth/restv1/token`. Grant types include `authorization_code` and `refresh_token`.

## Envelope

Every response looks like `{"StatusCode": 200, "Message": "Thanks for using EasyVisit", "Data": ...}`. Errors carry a non-200 `StatusCode` (for example 404 with `"Unable to find locations"`) and `Data: null`.

## Public endpoints (no auth)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/Location/{locationId}` | Practice details, opening hours, `photoData` (base64 JPEG) |
| GET | `/api/v1/Location/{locationId}/appointmenttypes` | `[{apptTypeID, name, description, telehealthType}]` |
| GET | `/api/v1/Location/{locationId}/appointmenttypes/{apptTypeId}/resources` | **Every doctor and every open slot** in the booking window. This is the only call the integration polls. |
| GET | `/api/v1/Location/{locationId}/availableslots?ResourceId=&ApptTypeID=&FromDate=YYYY-MM-DD&ToDate=YYYY-MM-DD` | One doctor, a date range; `Data` is the same `availableSlotDates` shape |
| GET | `/api/v1/application/disclaimer` | |

The booking page URL is `https://web.easyvisit.com.au/booking/{locationId}/{apptTypeId}`.

### Resource record

```
resourceId, name, gender, appointmentLength (min), nextAvailableSlot,
availableSlotDates: [{date, slots: [{resourceId, dateTime}], timeZoneId}],
manualConfirm, notesForPatients, billingInfo, specialties, languages,
photoData (base64, large), bio, ...
```

## Quirks

- **Slot times are naive local times.** `timeZoneId` is a *Windows* zone name (`"Tasmania Standard Time"`), mapped in `slots.py`. Tasmania changes to daylight saving on the first Sunday of October, so localise every slot, never apply a fixed offset.
- The resources response is about 225 KB for 12 doctors, almost all of it `photoData`. The client drops `photoData` and `bio` right away.
- The booking window is about 6 weeks. A new day appears at the end of the window each day.
- A doctor with nothing open still appears, with `availableSlotDates: []` and `nextAvailableSlot: null`.
- `manualConfirm: true` means the practice must approve a web booking before it is confirmed.

## Booking (authenticated; not used yet, for phase 2)

The web app sends `Authorization: Bearer <accessToken>` (from the OIDC code + PKCE flow) and `Content-Type: application/json`.

1. `POST /api/v1/Booking/SlotLock` `{dateTime, resourceID, locationID[, oldLockID]}` → `Data.lockID`. HTTP 409 means the slot is already taken.
2. `POST /api/v1/Booking/ValidateMultipleBooking` `{dateTime, locationId, familyMemberId}` → `Data` is `"true"` if the patient already has a booking that day.
3. `GET /api/v1/User` (the account holder), `GET /api/V1/user/related` (family members, used for `FamilyMemberId`).
4. `POST /api/v3/Booking` `{dateTime, resourceID, locationID, appointmentTypeID, lockID, FamilyMemberId, contactNumber, contactEmail, contactName, MultipleAptBookingNotes, Token, AppointmentBookedFrom: "Web"}` → `Data.isManualConfirm`.

Still unknown: what `Token` must hold for a signed-in booking. For guest bookings it appears to be a reCAPTCHA token. Signed-in users don't see a captcha, so it is probably empty. Confirm with one real booking.

Other endpoints the web app uses: `POST /api/v2/Otp/GenerateOTP` (guest; reCAPTCHA v2/v3), `POST /api/v1/Otp/ConfirmOTP`, `POST /api/v1/Booking/CancelAppoinmentByToken` (sic), `GET /api/V1/Booking/AllowCancelAppointment`.
