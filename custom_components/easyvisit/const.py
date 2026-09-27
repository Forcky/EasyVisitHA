"""Constants for the EasyVisit integration."""
DOMAIN = "easyvisit"

# API
API_BASE = "https://api.easyvisit.com.au"
BOOKING_URL = "https://web.easyvisit.com.au/booking/{location_id}/{appt_type_id}"
EXAMPLE_BOOKING_URL = "https://web.easyvisit.com.au/booking/123/456"

# Config entry data
CONF_LOCATION_ID = "location_id"
CONF_LOCATION_NAME = "location_name"
CONF_APPT_TYPE_ID = "appt_type_id"
CONF_APPT_TYPE_NAME = "appt_type_name"

# Config entry options
CONF_WATCHES = "watches"  # {"<resourceId>": "<doctor name>"}; "0" = any doctor
CONF_NOTIFY_TARGETS = "notify_targets"  # ["notify.mobile_app_pixel", ...]
CONF_SCAN_INTERVAL = "scan_interval"  # minutes

DEFAULT_SCAN_INTERVAL = 5
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 60

# Pseudo-resource that watches every doctor at the practice.
ANY_DOCTOR = 0

# Per-watch settings (held in the coordinator's Store, not the config entry,
# so changing them from an entity doesn't reload the integration).
DEFAULT_CUTOFF_DAYS = 14
# The whole practice has hundreds of slots a fortnight out; "anything by
# tomorrow-ish" is the useful question there.
DEFAULT_CUTOFF_DAYS_ANY = 2
MIN_CUTOFF_DAYS = 0
MAX_CUTOFF_DAYS = 60

EVENT_SLOT_AVAILABLE = "easyvisit_slot_available"

STORAGE_VERSION = 1

# How many slots to list in a notification / entity attributes.
NOTIFY_MAX_SLOTS = 5
ATTR_MAX_SLOTS = 10
