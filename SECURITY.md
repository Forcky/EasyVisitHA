# Security

Please report vulnerabilities privately through GitHub's **Report a vulnerability** button (Security tab), not in a public issue.

## What this integration handles

- **Phase 1 (current):** only the public availability data of HotDoc and EasyVisit. It needs no credentials and stores none. Per-doctor settings and the list of slots already announced are kept in Home Assistant's `.storage`.
- **Notify targets** are limited to `notify.<service>`. Other services are rejected by the config flow and ignored at runtime.
- **Responses** over 10 MB are refused.
- **Phase 2 (planned):** auto-booking will store booking-site OAuth tokens in the config entry, the standard Home Assistant practice. Those tokens must never be logged.
