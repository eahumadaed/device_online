# Security Policy

## Supported Versions

Security fixes are handled on the latest public branch.

## Reporting a Vulnerability

Please report security issues privately through the repository security advisory
workflow, or by contacting the maintainer through the private channel listed on
the project profile.

Do not open public issues for vulnerabilities, leaked credentials, real device
serials, packet captures, private endpoint lists, or deployment details.

## Sensitive Data

This repository must not contain:

- Private credentials, tokens, passwords, or API keys.
- Real device serial numbers or customer data.
- Packet captures or traffic logs.
- Vendor SDKs, DLLs, or proprietary binaries.
- Private IP addresses, private endpoint pools, workstation paths, or deployment hostnames.
- CSV exports or operational result files.

Use environment variables for operational configuration and synthetic examples
for tests and documentation.
