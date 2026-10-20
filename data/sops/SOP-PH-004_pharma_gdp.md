# SOP-PH-004: Pharmaceutical Good Distribution Practice (GDP) Handling

Owner: Pharma Quality Unit · Revision 9 · Effective 2026-02-20 · Applies to cargo_class PHARMA

## 1. Scope
Applies to all 2–8 °C medicinal products (vaccines, biologics, insulin). Complements SOP-TC-001 and SOP-EX-002; where they differ, this SOP prevails for PHARMA cargo.

## 2. Door-open limits
- Door openings are only permitted at origin, destination and GDP-certified facilities.
- Any door_open event during transit is a GDP deviation and must be logged (ESCALATE_QA) even if temperature stays in range.
- A door-open event that coincides with a cargo temperature above 8 °C for more than 15 minutes requires QA quarantine assessment of the full load (QUARANTINE action) before the customer may use the product.

## 3. Excursion tolerance for pharma
There is no "minor excursion" allowance for PHARMA cargo: every reading above 8 °C or below 2 °C is reportable. Stability budget decisions (use of manufacturer stability data) are made only by the Pharma Quality Unit, never by dispatch.

## 4. Diversions
PHARMA cargo may only be diverted or cross-docked at facilities with gdp_certified = 1. Non-GDP facilities must not be used even in emergencies; instead dispatch a rescue reefer.

## 5. Customer notification
The consignee's pharmacist / QP must be notified (CUSTOMER_NOTIFY) of any deviation before delivery, including the deviation record reference.
