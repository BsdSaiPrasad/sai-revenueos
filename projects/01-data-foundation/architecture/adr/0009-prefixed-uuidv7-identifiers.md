# ADR-0009: Generate Entity-Prefixed UUIDv7 Canonical IDs

- **Decision ID:** D009 (P1.2 Decision A)
- **Status:** Accepted and implemented in the reference layer
- **Scope:** P1 canonical identity creation

## Connected Example

**Example:** Globex Health receives a permanent Account identifier before it rebrands and changes its domain.

**Problem:** A Salesforce identifier, company name, domain, or sequential number would either change, couple RevenueOS to one vendor, or require central allocation.

**Our Solution:** RevenueOS assigns an entity prefix plus Universally Unique Identifier version 7 (UUIDv7), so the Account ID stays stable, recognizable, and roughly time ordered.

## Options considered

- Vendor IDs couple RevenueOS to one system.
- Sequential integers are compact but require centralized allocation and reveal volume.
- Random Universally Unique Identifier version 4 (UUIDv4) values are portable but do not provide creation-time ordering.
- Entity-prefixed UUIDv7 values combine readable type context, distributed uniqueness, and time ordering.

## Decision and technical design

Generate a Request for Comments (RFC) 9562 UUIDv7 and prepend a controlled entity prefix such as `sai_acc_`, `sai_person_`, or `sai_opp_`. IDs are permanent and non-reusable. P1 owns creation authority. The implementation validates version and variant, detects a collision, and retries safely without assuming the host Python has `uuid.uuid7()`.

## Tradeoffs

IDs are longer than integers, the prefix registry requires governance, and UUIDv7 time bits reveal approximate creation time. The benefit is source independence and reliable distributed generation.

## Interview explanation

“I used controlled entity prefixes plus standards-compliant UUIDv7 so IDs are readable, globally unique, roughly time ordered, and never tied to a vendor record.”
