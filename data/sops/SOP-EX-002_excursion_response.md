# SOP-EX-002: Temperature Excursion Response Protocol

Owner: Quality Assurance & Dispatch Operations · Revision 5 · Effective 2026-03-01

## 1. Definitions
- Excursion: any cargo temperature reading outside the allowed range defined in SOP-TC-001.
- Minor excursion: excursion of no more than 2 °C beyond the limit lasting no more than 30 minutes in total, with temperature recovered into range.
- Major excursion: excursion of more than 2 °C beyond the limit, OR lasting more than 30 minutes cumulative, OR any excursion that has not recovered.
- Critical excursion: frozen or deep-frozen cargo above -12 °C at any time, or PHARMA cargo above 12 °C or below 0 °C at any time (freeze damage).

## 2. Immediate response (first 15 minutes)
1. Dispatcher confirms the reading is not a sensor fault by checking consecutive readings and reefer_status.
2. Contact the driver to verify reefer operation, door closure and fuel level.
3. Log an ESCALATE_QA dispatch action for any major or critical excursion.
4. Do not open the trailer doors to "check" the cargo unless instructed by QA.

## 3. Escalation tiers
| Tier | Trigger | Notify | Target response |
|---|---|---|---|
| Tier 1 | Minor excursion, recovered | Dispatch supervisor (log only) | 1 hour |
| Tier 2 | Major excursion or reefer DEGRADED with rising trend | QA on-call + customer account manager | 15 minutes |
| Tier 3 | Critical excursion or reefer FAULT | QA director + customer + insurance desk | Immediate |

## 4. Equipment-driven excursions
When an excursion or rising trend coincides with reefer_status DEGRADED or FAULT, follow SOP-EQ-005 (Reefer Equipment Failure). The default action is to divert to the nearest compatible cold-storage facility for cross-dock transfer if the facility can be reached before the cargo exceeds critical limits.

## 5. Cargo disposition
Cargo involved in a major or critical excursion must be placed on QA HOLD (QUARANTINE action) at delivery. The consignee must be notified before arrival (CUSTOMER_NOTIFY action). QA alone decides release, rework or destruction.

## 6. Documentation
Every excursion requires a deviation record containing: shipment ID, start/end timestamps, peak temperature, duration, root cause, and the corrective actions taken.
