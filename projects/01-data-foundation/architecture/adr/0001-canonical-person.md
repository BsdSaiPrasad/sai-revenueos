# ADR-0001: One Canonical Person Represents One Human

- **Decision ID:** D001
- **Status:** Accepted
- **Scope:** P1 canonical identity

## 1. The Problem

The same human can appear in a Customer Relationship Management (CRM) system, marketing platform, product application, and support tool. Treating every record as a different person creates duplicates and breaks history.

## 2. Connected Example

**Example:** Sarah Kim appears as a Salesforce Lead, a HubSpot contact, and a product user before moving from Globex Health to Northstar Labs.

**Problem:** Treating each record or employer change as a new person would duplicate Sarah and split her history.

**Our Solution:** One durable Person represents Sarah, while source records and effective-dated employment relationships preserve where each fact came from.

## 3. Options We Considered

- Create a different Person for each source record. This is simple but produces duplicates.
- Use email as the Person ID. Email can change, be shared, or be missing.
- Create one source-independent Person and connect source and employment records separately.

## 4. Our Decision

Create one durable canonical `Person` for one human across source systems, lifecycle stages, and employers.

## 5. How It Works Technically

- `Person.person_id` is the stable canonical identity.
- Salesforce Leads, Contacts, HubSpot contacts, and product profiles remain `SourceRecord` objects.
- `ExternalIdentityCrosswalk` maps confirmed source records to Person.
- `AccountPersonRelationship` stores Sarah's effective-dated employment at Globex Health and Northstar Labs.

## 6. Why We Chose It

The human is more stable than an email address, employer, or CRM lifecycle. This design preserves a continuous view of the person while keeping source evidence and employer history.

## 7. Tradeoffs and Limitations

This model requires identity resolution, relationship history, and safe merge/unmerge controls. A bad match can affect many downstream records, so later phases must use conservative rules and auditability.

## 8. Interview Explanation

“I separated a person's permanent identity from CRM records and employment relationships. That lets one person appear in several systems or change employers without creating duplicate identities or losing history.”
