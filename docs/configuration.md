# Configuration

## Adding the integration

Settings → Devices & services → **Add integration** → **EasyVisit GP Availability**.

### 1. Practice

Enter the practice's EasyVisit **location ID**, or paste its booking link. To find it:

1. Open the practice's online booking page. It usually looks like `https://web.easyvisit.com.au/booking/123/456`.
2. The first number is the location (`123`), and the second is the appointment type (`456`).

If you paste the full link, the appointment type is preselected in the next step.

### 2. Appointment type

These are the practice's own types, e.g. *Standard appt.*, *Long appt.*, *Telephone consult*. Each practice + appointment type pair is a separate integration entry. To watch Standard and Long appointments, add the integration twice.

### 3. Doctors and notifications

| Field | Meaning |
|---|---|
| **Doctors to watch** | Each ticked doctor becomes a device. The list shows each doctor's next available date. *Any doctor at …* watches the whole practice. |
| **Notify services** | Where alerts go, e.g. `notify.mobile_app_pixel_8`. Choose several or none. With none, only the event fires. You can also type a service name that isn't in the list. |
| **Check every** | Minutes between checks (2–60, default 5). One request covers every doctor. |

## Changing options later

Settings → Devices & services → EasyVisit GP Availability → **Configure**. You can change the watched doctors, notify services, and check interval. The integration reloads when you save.

- Doctors you untick are removed along with their devices.
- If a doctor stops offering that appointment type, they stay watched and are shown as *not listed right now*.

## Entities

Each watched doctor is a device, grouped under the practice device.

| Entity | Type | Notes |
|---|---|---|
| `sensor.<doctor>_next_available` | timestamp | The earliest open slot. Attributes: `open_slots`, `next_slots` (up to 10 × `{doctor, resource_id, start}`), `booking_url`, `notes`, `manual_confirm` |
| `sensor.<doctor>_slots_before_cutoff` | count | Attributes: `cutoff` (date), `slots` (up to 10) |
| `binary_sensor.<doctor>_slot_before_cutoff` | on/off | On when anything is open on or before the cutoff date |
| `number.<doctor>_cutoff` | days (0–60) | See below |
| `switch.<doctor>_notifications` | on/off | Mutes notify services for this doctor. The event still fires. |
| `button.<doctor>_send_test_notification` | button | Sends what is open before the cutoff now, marked `[Test]` |
| `sensor.<practice>_last_checked` | timestamp | Diagnostic: when availability was last fetched |

The cutoff and notification settings are kept by the integration itself. They survive restarts and don't reload anything when you change them.

## Choosing a cutoff

A slot counts when it falls **on or before today + cutoff days** (calendar days, in the practice's time zone):

| Cutoff | Counts |
|---|---|
| 0 | Today only |
| 1 | Today and tomorrow |
| 14 | Anything up to two weeks from today |

Tips:
- Set it just short of your doctor's current *Next available*. For example, if the next slot is 26 days away, a cutoff of 14 alerts you to cancellations in the next fortnight.
- EasyVisit only shows about **6 weeks** ahead, so anything larger has no extra effect.
- The cutoff rolls forward each day. Slots already open that come inside the window are announced when they do.
- *Any doctor* at a busy practice can have hundreds of slots a fortnight out. That's why it defaults to 2 days with notifications off.

## Defaults

| Setting | Doctor | Any doctor |
|---|---|---|
| Cutoff | 14 days | 2 days |
| Notifications | on | off |
