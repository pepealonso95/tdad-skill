# Privacy Policy

**TDAD — Test-Driven AI Development**
Last updated: 2026-03-24

## Summary

TDAD runs entirely on your local machine. It does not collect, transmit, or store any personal data or telemetry.

## Data Collection

TDAD does **not** collect any data. Specifically:

- **No telemetry** — No usage statistics, crash reports, or analytics are sent anywhere.
- **No network requests** — TDAD makes zero outbound network connections. All parsing, indexing, and analysis happens locally.
- **No user accounts** — There is no sign-up, login, or authentication.
- **No cookies or tracking** — TDAD is a CLI tool and has no web component.

## Data Processing

When you run `tdad index`, TDAD reads source files in your repository to build a local dependency graph. This graph is stored on disk inside your repository at `.tdad/graph.pkl` and `.tdad/test_map.txt`. These files never leave your machine.

## Third-Party Services

TDAD does not integrate with or send data to any third-party services. The optional Neo4j backend connects only to a Neo4j instance that you configure and control.

## Open Source

TDAD is open source under the MIT License. You can audit the full source code at:
https://github.com/pepealonso95/tdad-skill

## Contact

If you have questions about this privacy policy, contact:
Pepe Alonso — pepe@berkeley.edu
