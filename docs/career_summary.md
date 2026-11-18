# Career summary

**FR**

- Développement d’un benchmark chronologique à J-1 entre l’Allemagne et l’Autriche, avec coupe des observations postérieures à l’heure d’émission.
- Mesure du transfert sur 6 575 heures par zone et comparaison d’intervalles à 80 % calibrés hors test.

**EN**

- Built a Germany–Austria day-ahead load benchmark with issuance-aware features and purged rolling validation.
- Evaluated cross-area transfer and interval coverage on 6,575 held-out hours per area.

## Demonstrated skills

Time-series feature engineering, temporal validation, structured transfer learning, error analysis, ML calibration and daylight-saving handling.

## Interview questions

- Where can a 24-hour lag leak into a forecast issued at noon the previous day?
- How does UTC support unambiguous local-hour predictions across clock changes?
- Why express the target relative to an area-specific scale?
- Which measurements track transfer error and interval quality separately?

## Two-minute explanation

Issue forecasts for the next local delivery date at noon. Build features from past UTC lags and calendar terms, normalize within area using available weeks, and hold out 2020. Compare weekly persistence, Ridge and histogram boosting. German MAE drops from 2,226.65 MW to 1,674.21 MW with the local model. Austrian interval coverage drops from 81.3% to 73.6% when transferring the German model and calibration.

## Five-minute explanation

Show DST examples and the forecast-origin contract. Walk through three rolling 2019 folds with training labels strictly before each fold's first issue time. Compare model transfer in both directions against the same time-matched weekly baseline. Explain relative residual intervals and how an interval transferred from a different area changes width and coverage. Discuss the limits of retrospective revisions and explain the conditional feature ablations without using them to re-select models.

## Follow-up experiments

Add weather forecasts available at issuance, publication delays, public holiday calendars and drift monitoring on a newer archive.
