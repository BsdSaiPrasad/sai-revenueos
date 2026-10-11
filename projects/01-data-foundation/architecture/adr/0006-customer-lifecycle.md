# ADR-0006: Customer Is an Account Lifecycle Status

- **Decision ID:** D006
- **Status:** Accepted
- **Scope:** P1 commercial identity

## 1. The Problem

A prospect can become a customer, renew, pause service, or stop being a customer. Creating a second company record when this happens would split the organization's history.

## 2. Connected Example

**Example:** Globex Health begins as a prospect, signs a Contract, and starts a Subscription.

**Problem:** Creating a second Customer record would split its marketing, sales, billing, product, and support history across two company identities.

**Our Solution:** Globex keeps one Account whose lifecycle can become customer, while Contract and Subscription retain their own identities and histories.

## 3. Options We Considered

- Create a separate Customer entity that duplicates the Account. This fragments company identity.
- Infer customer state independently in every report. This produces inconsistent answers.
- Keep one Account and represent customer as governed lifecycle status while preserving commercial entities separately.

## 4. Our Decision

Customer is a business lifecycle status associated with `Account`, not another company identity. `Contract` and `Subscription` remain independent entities with their own identities and histories.

## 5. How It Works Technically

- `Account.lifecycle_status` carries the governed business state.
- `customer_since_at` and `ended_customer_at` provide selected lifecycle timing.
- Contract records signed agreements.
- Subscription records time-bounded service entitlement.
- The authoritative rule that derives customer status is deliberately deferred.

## 6. Why We Chose It

Marketing, sales, billing, product, and support facts stay attached to one Account throughout its lifecycle. Commercial agreements remain detailed rather than being reduced to a label.

## 7. Tradeoffs and Limitations

Customer status requires one future governed derivation rule and clear write authority. Until that rule is approved and implemented, the architecture must not claim to calculate customer status operationally.

## 8. Interview Explanation

“I modeled customer as a lifecycle state on Account, not a duplicate company. Contracts and subscriptions stay separate so the commercial history remains accurate.”
