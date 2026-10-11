# ADR-0005: Give Each Opportunity One Primary Account and Many People

- **Decision ID:** D005
- **Status:** Accepted
- **Scope:** P1 revenue model

## 1. The Problem

A sales Opportunity needs one clear buying company, but a Business-to-Business (B2B) purchase usually involves several people with different roles.

## 2. Connected Example

**Example:** Globex Health evaluates an analytics product with Sarah Kim as champion, John Lee as economic buyer, and Emily Chen as technical evaluator.

**Problem:** Repeating person columns would limit the buying committee, while multiple primary Accounts would make pipeline ownership unclear.

**Our Solution:** The Opportunity has one primary Globex Account, and OpportunityPersonRole stores any number of people with explicit roles.

## 3. Options We Considered

- Store several contact columns on Opportunity. This limits the buying committee and makes roles hard to extend.
- Allow several primary Accounts. This makes pipeline and revenue attribution ambiguous.
- Require one primary Account and use a relationship entity for participating Persons.

## 4. Our Decision

Every canonical `Opportunity` has exactly one primary buying `Account`. People participate through `OpportunityPersonRole`, which records their specific roles.

## 5. How It Works Technically

- `Opportunity.primary_account_id` points to the buying Account.
- `OpportunityPersonRole.opportunity_id` and `person_id` connect one Person to one Opportunity.
- `role_type`, `influence_level`, and `is_primary_contact` describe participation.
- `valid_from` and `valid_to` preserve role changes.

## 6. Why We Chose It

One primary Account makes pipeline ownership clear. The relationship table supports any number of people and roles without changing the Opportunity schema.

## 7. Tradeoffs and Limitations

Buying-committee queries require a join. Future partner, reseller, or multi-account deal roles must be modeled explicitly rather than weakening the primary-Account rule.

## 8. Interview Explanation

“I gave each Opportunity one primary buying Account for clear attribution and modeled the buying committee through a role table, so any number of people can participate with changing roles.”
