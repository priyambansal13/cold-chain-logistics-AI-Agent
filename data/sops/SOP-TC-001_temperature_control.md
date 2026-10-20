# SOP-TC-001: Temperature Control Ranges by Cargo Class

Owner: Quality Assurance · Revision 7 · Effective 2026-01-15 · Applies to all reefer road transport.

## 1. Purpose and scope
This SOP defines the mandatory cargo temperature ranges for every cargo class carried by the fleet. The cargo_class field in the telemetry database maps directly to the classes below. The "cargo temperature" is the return-air / product probe reading (cargo_temp_c), NOT the reefer setpoint and NOT ambient temperature.

## 2. Mandatory temperature ranges (temp range table)
| Cargo class | Typical goods | Allowed range (inclusive) | Nominal setpoint |
|---|---|---|---|
| FROZEN | Frozen meat, seafood, frozen ready meals | -22 °C to -18 °C | -20 °C |
| DEEP_FROZEN | Ice cream, gelato, sorbet, specialty frozen desserts | -28 °C to -23 °C | -25.5 °C |
| CHILLED | Fresh seafood, shellfish, dairy | 0 °C to +4 °C | +2 °C |
| PHARMA | Vaccines, biologics, insulin (2–8 °C products) | +2 °C to +8 °C | +5 °C |
| FRESH_PRODUCE | Berries, leafy greens, cut fruit | +1 °C to +7 °C | +3.5 °C |

Frozen cargo limit: -22C to -18C. Deep frozen / ice cream limit: -28C to -23C. Chilled limit: 0C to 4C. Pharma limit: 2C to 8C. Fresh produce limit: 1C to 7C.

## 3. Status classification
- ON TRACK (green): latest cargo temperature inside the allowed range and more than 0.5 °C from either limit, with no adverse trend.
- AT RISK (amber): cargo temperature within 0.5 °C of either limit (alert band), OR the temperature trend projects a breach of a limit within the next 2 hours, OR reefer_status is HIGH_LOAD / DEGRADED, OR a route weather threat is active per SOP-WX-003.
- EXCURSION (red): any reading outside the allowed range. Handle under SOP-EX-002.

## 4. Trend analysis rule
Dispatchers and automated agents must evaluate the trend over at least the last 2 hours of readings (8 readings at 15-minute intervals). If the average rate of change would carry the cargo across a limit within 2 hours, the shipment is AT RISK and proactive intervention is required before the breach occurs.

## 5. Reefer setpoint discipline
Reefer setpoints must be programmed at the nominal setpoint in section 2. Drivers may never change setpoints without dispatcher authorisation logged in the dispatch system.
