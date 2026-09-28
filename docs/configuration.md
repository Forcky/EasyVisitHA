# Configuration

## Adding the integration

Settings → Devices & services → **Add integration** → **GP Availability**.

### 1. Practice

Paste the link to the practice's online booking page. The integration works out the booking site from the link.

| Site | What to paste |
|---|---|
| **HotDoc** | The practice's page, e.g. `https://www.hotdoc.com.au/medical-centres/kingston-TAS-7050/<practice>/doctors`. A link to one doctor's page (`…/doctors/<doctor>`) also works and preselects that doctor. |
| **EasyVisit** | The booking page, e.g. `https://web.easyvisit.com.au/booking/123/456`, or just the location number (`123`). The second number (`456`) is the appointment type, which is then preselected. |

### 2. Appointment type

These are the practice's own types, e.g. *Standard appt.* or *Long appt.*. Each practice + appointment type pair is a separate integration entry. To watch Standard and Long appointments, add the integration twice.

On **HotDoc**, each type is listed once for existing patients and once for new patients, when the practice offers both. They can have different availability, so pick the one that applies to you.

### 3. Doctors and notifications

| Field | Meaning |
|---|---|
| **Doctors to watch** | Each ticked doctor becomes a device. The list shows each doctor's next available date. *Any doctor at …* watches the whole practice. |
| **Notify services** | Where alerts go, e.g. `notify.mobile_app_pixel_8`. Choose several or none. With none, only the event fires. You can also type a service name that isn't in the list. |
| **Check every** | Minutes between checks. Default: HotDoc 10 (5–60), EasyVisit 5 (2–60). |

Requests per check:
- **EasyVisit:** one request covers every doctor.
- **HotDoc:** one request per 7 days up to the longest cutoff, covering every watched doctor. The default 14-day cutoff takes 3 requests.

## Changing options later

Settings → Devices & services → GP Availability → **Configure**. You can change the watched doctors, notify services and check interval. The integration reloads when you save.

- Doctors you untick are removed along with their devices.
- If a doctor stops offering that appointment type, they stay watched and are shown as *not listed right now*.

## Entities

Each watched doctor is a device, grouped under the practice device.

| Entity | Type | Notes |
|---|---|---|
| `sensor.<doctor>_next_available` | timestamp | The earliest open slot. Attributes: `open_slots`, `next_slots` (up to 10 × `{doctor, resource_id, start}`), `booking_url`, `notes`, and `manual_confirm` (EasyVisit only) |
| `sensor.<doctor>_slots_before_cutoff` | count | Attributes: `cutoff` (date), `slots` (up to 10) |
| `binary_sensor.<doctor>_slot_before_cutoff` | on/off | On when anything is open on or before the cutoff date |
| `number.<doctor>_cutoff` | days (0–60) | See below |
| `switch.<doctor>_notifications` | on/off | Mutes notify services for this doctor. The event still fires. |
| `button.<doctor>_send_test_notification` | button | Sends what is open before the cutoff now, marked `[Test]` |
| `sensor.<practice>_last_checked` | timestamp | Diagnostic: when availability was last fetched |

On HotDoc, only slots up to the longest cutoff are fetched, so `open_slots` and `next_slots` stop there. **Next available** still shows the doctor's next opening beyond it, because HotDoc reports that separately.

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
- EasyVisit only shows about **6 weeks** ahead, so anything larger has no extra effect there.
- On HotDoc, each extra week of cutoff adds a request per check.
- The cutoff rolls forward each day. Slots already open that come inside the window are announced when they do.
- *Any doctor* at a busy practice can have hundreds of slots a fortnight out. That's why it defaults to 2 days with notifications off.

## Defaults

| Setting | Doctor | Any doctor |
|---|---|---|
| Cutoff | 14 days | 2 days |
| Notifications | on | off |
