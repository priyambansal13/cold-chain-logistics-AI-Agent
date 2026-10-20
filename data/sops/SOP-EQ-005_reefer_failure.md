# SOP-EQ-005: Reefer Equipment Failure and Breakdown

Owner: Fleet Maintenance & Dispatch · Revision 3 · Effective 2025-11-30

## 1. Reefer status codes
- OK: normal operation.
- HIGH_LOAD: unit at maximum capacity, usually due to high ambient temperature; monitor trend.
- DEGRADED: unit cannot hold setpoint (compressor, refrigerant or airflow issue). Cargo temperature typically drifts upward.
- FAULT: unit failed or stopped.

## 2. Response to DEGRADED
1. Driver performs a roadside check (defrost cycle, evaporator airflow, fuel) within 30 minutes.
2. Dispatcher raises a MAINTENANCE_DISPATCH action to send a mobile reefer technician.
3. If the cargo trend projects a limit breach within 2 hours (see SOP-TC-001 §4), immediately divert to the nearest compatible cold-storage facility (DIVERT_COLD_STORAGE) for cross-dock into a healthy trailer. The facility must support the cargo class and have enough available pallets.

## 3. Response to FAULT
Immediate diversion to the nearest compatible cold-storage facility if reachable within 2 hours; otherwise dispatch a rescue reefer truck to the vehicle's location. Escalate as Tier 3 under SOP-EX-002.

## 4. Choosing a facility
Use the closest facility that (a) supports the cargo class, (b) has available pallets ≥ the shipment's pallet count, and (c) is open 24 hours when arrival is outside business hours. PHARMA additionally requires a GDP-certified facility (SOP-PH-004).
