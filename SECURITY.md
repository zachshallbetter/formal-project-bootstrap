# Security Policy

## Supported releases

Security fixes are applied to the current release line unless a maintainer explicitly declares otherwise.

## Reporting

Do not publish credentials, tokens, private endpoints, or exploitable details in a public issue. Use the repository host's private security-reporting channel when available.

A useful report includes the affected version, boundary, expected invariant, observed behavior, reproduction conditions, and likely impact. Do not include live secrets.

## Bootstrap security boundary

This repository defines operating patterns; it does not grant access to external services. Generated projects must bind service operations explicitly. Tool availability is never authority.
