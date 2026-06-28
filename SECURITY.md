# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

If you discover a security vulnerability in this package, please report it by emailing **ezraair555@gmail.com**.

Please do not open a public GitHub issue for security-related bugs.

We will acknowledge receipt within 48 hours and aim to provide a fix or mitigation within 14 days.

## PII Considerations

`pyduck-ona-profile` is designed to operate on HR data, which is sensitive by definition. The package itself does not enforce access control beyond the `Subject.with_role()` redaction helper — production deployments are responsible for:

- Authentication and authorization at the application layer.
- Encryption of HR data at rest and in transit.
- Audit logging of every `Subject.profile()` and `ask()` call.
- Compliance with applicable data protection regulations (GDPR, CCPA, etc.).

The package's only network call is the optional download of the `BAAI/bge-small-en-v1.5` model from Hugging Face on first use. After that initial download, no further network calls are made.
