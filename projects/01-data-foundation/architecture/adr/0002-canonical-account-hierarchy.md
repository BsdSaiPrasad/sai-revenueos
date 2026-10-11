# ADR-0002: Keep Parent and Subsidiary Accounts Separate

- **Decision ID:** D002
- **Status:** Accepted
- **Scope:** P1 organization identity

## 1. The Problem

A corporate group can contain a parent company and several subsidiaries. Sales, contracts, product use, and support may happen at different levels of that hierarchy.

## 2. Connected Example

**Example:** Helio Systems owns Globex Health, but Globex signs its own contract and supports its own users.

**Problem:** Combining them into one Account would attach Globex revenue and activity to the wrong legal or operating company.

**Our Solution:** Each company keeps its own Account, and an effective-dated hierarchy relationship connects the parent to the subsidiary.

## 3. Options We Considered

- Flatten the group into one Account. Reporting is easy, but entity-level facts become inaccurate.
- Copy parent fields onto each subsidiary. This duplicates data and loses history when ownership changes.
- Give each organization its own Account and connect them with explicit relationships.

## 4. Our Decision

Parent companies and subsidiaries receive independent canonical `Account` identities connected through `AccountHierarchyRelationship`.

## 5. How It Works Technically

- Both Helio Systems and Globex Health have their own `account_id`.
- `AccountHierarchyRelationship.parent_account_id` points to Helio Systems.
- `child_account_id` points to Globex Health.
- `valid_from` and `valid_to` preserve changes in ownership over time.
- Self-links and hierarchy cycles are invalid.

## 6. Why We Chose It

The design keeps contracts, revenue, users, and support attached to the correct organization while still supporting parent-level rollups.

## 7. Tradeoffs and Limitations

Queries need hierarchy traversal, and later validation must prevent cycles or conflicting active parents. That extra work is preferable to losing legal and operational detail.

## 8. Interview Explanation

“I modeled parents and subsidiaries as separate Accounts with effective-dated hierarchy edges. This preserves entity-level revenue and contracts while still allowing corporate-family reporting.”
