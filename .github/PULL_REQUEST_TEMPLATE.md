## Contributor Checklist

- [ ] All added or modified fixtures and demo data are synthetic and stay in
      the synthetic namespace: DEMO or TSTV court code, case type `測`, and
      future dates. No real case data, national-ID-shaped strings,
      credentials, or local machine paths are included.
- [ ] Full local validation battery was run: both guard scripts, ruff, pytest,
      and the demos.
- [ ] No trust-gate default behavior was loosened; any relaxation is explicit
      opt-in, default OFF, and covered by a fail-closed negative test.

## Summary

Describe the change and the validation evidence.
