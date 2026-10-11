# ADR-0003: Preserve Important Account History Selectively

- **Decision ID:** D003
- **Status:** Accepted
- **Scope:** P1 temporal modeling

## 1. The Problem

Company names, domains, and parent relationships change. Overwriting the current value makes past reports and identity decisions difficult to explain.

## 2. Connected Example

**Example:** Globex Health rebrands to Helio Health and changes its primary domain after closing an Opportunity.

**Problem:** Overwriting the old name and domain would make last year's report show facts that were not valid at that time.

**Our Solution:** Selective Slowly Changing Dimension Type 2 (SCD Type 2) history closes the old values and starts new effective-dated rows without changing the Account ID.

## 3. Options We Considered

- Keep only the latest value. This is simple but destroys history.
- Apply SCD Type 2 to every Account attribute. This preserves everything but creates unnecessary complexity.
- Preserve history only for attributes with a clear as-of business need.

## 4. Our Decision

Use selective SCD Type 2 semantics for Account names, domains, and hierarchy relationships. Do not apply SCD Type 2 blindly to every table or field.

## 5. How It Works Technically

- `AccountNameHistory` stores legal names, trade names, aliases, and preferred-name intervals.
- `AccountDomainHistory` stores normalized domains and primary-domain intervals.
- `AccountHierarchyRelationship` stores effective-dated parent/child links.
- `valid_from` is inclusive, `valid_to` is exclusive, and null `valid_to` means current.

## 6. Why We Chose It

These attributes matter for identity resolution, attribution, and as-of reporting. Selective history preserves that value without turning every entity into a complex history model.

## 7. Tradeoffs and Limitations

Queries need time-aware joins, and future tests must prevent overlapping preferred or primary intervals. Attributes not selected for history will rely on source history or later requirements.

## 8. Interview Explanation

“I used SCD Type 2 only for identity-sensitive Account attributes such as name, domain, and hierarchy. That supports as-of analysis without adding history complexity everywhere.”
