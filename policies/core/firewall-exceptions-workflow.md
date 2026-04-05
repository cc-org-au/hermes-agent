<!-- policy-read-order-nav:top -->
> **Governance read order** — step 2 of 61 in the canonical `policies/` sequence (layer map & tables: [`README.md`](../README.md)).
> **Before this file:** read [core/security-first-setup.md](security-first-setup.md) and everything earlier in that sequence. **Do not** interpret this document as authoritative until those prerequisites are satisfied.
> **This file:** safe to apply only after the prerequisite above (if any) is complete.
<!-- policy-read-order-nav:top-end -->

# Firewall Exceptions Workflow

Use this workflow for any change to host firewall rules, especially outbound allowlist changes.

## Principles

- Keep default-deny inbound and outbound as the baseline.
- Add the smallest possible exception (port, protocol, destination scope).
- Time-box temporary exceptions and set an expiry.
- Record business/operational justification for every exception.

## Request Template

Copy this block into the ticket/PR:

```md
## Firewall Exception Request
- Requestor:
- Date:
- Environment/Host:
- Rule direction: inbound | outbound
- Protocol/port:
- Destination scope (CIDR/FQDN/service):
- Why required:
- Risk if not added:
- Compensating controls:
- Expiry date (if temporary):
- Rollback plan:
```

## Approval Gates

- Security owner approval required.
- Service owner approval required.
- No self-approval by requestor.

## Implementation Steps

1. Capture current rules as baseline.
2. Add minimal rule(s) with clear comments.
3. Validate only required connectivity.
4. Re-check exposed/listening ports.
5. Update baseline snapshot after approval.

## Verification Checklist

- Required integration works.
- No unexpected new listening ports.
- Public attack surface unchanged unless explicitly approved.
- Drift monitor still clean.

## Emergency Procedure

- For urgent incidents, apply temporary rule with an explicit expiry.
- Backfill formal request/approval within 24 hours.
- Remove or convert temporary rule after incident closure.

<!-- policy-read-order-nav:bottom -->
> **Next step:** continue to [core/unified-deployment-and-security.md](unified-deployment-and-security.md) after this file is fully read and applied. Do not skip ahead unless a human operator explicitly directs a narrower scope.
<!-- policy-read-order-nav:bottom-end -->
