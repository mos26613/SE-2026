# 0003. Anonymize personal data before sending it to the AI

- **Status:** Accepted
- **Date:** 2026-11-16
- **Deciders:** MASHAB team (recorded from the Project Initiation Document and Epic 5)

## Context

The AI features (chat agent, Appeal Assistant) work with files and text the student uploads, such as grader comments and the student's answers. These can contain names, ID numbers and email addresses. Sending them to an external AI service is a privacy risk.

This ADR covers only data sent to the AI (Epic 5). Protecting the user data we collect and store is a separate concern, handled in Epic 1 (User Story 1.3.4).

## Options considered

1. **Send data as-is.** Simplest, but exposes personal data to a third party.
2. **Rely on the client to remove personal data.** Easy to bypass and inconsistent.
3. **Mandatory anonymization middleware on the server.** Every AI request passes through one gateway that replaces personal data with placeholders and restores it locally in the response.

## Decision

Option 3. All Gemini calls go through the backend AI gateway (Feature 5.1). A mandatory middleware (Feature 5.2) removes ID numbers, names and email addresses before the request and restores them in the response on the server. The extension and the dashboard never call Gemini directly.

## Consequences

- No personal data reaches the AI provider.
- Anonymization rules need their own tests, including Hebrew names and Israeli ID number formats.
- Every AI request goes through one place, which also handles rate limits, quotas and error handling.
