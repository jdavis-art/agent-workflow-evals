# Factory Operations (fixture)

Fictional data for the seed-drift eval. The Line Loading table below is the
source of truth for the production-plan dashboard seed.

## Line Loading

| Project | Boxes | Status | $/box (contract) | Start |
| --- | --- | --- | --- | --- |
| Cedar Row | 24 | contracted | 71,000 | 2026-10-05 |
| Northline | 20 | contracted | 68,500 | 2026-11-02 |
| Pine Ridge | 36 | prospect | 74,000 | 2027-01-11 |
| Wasatch Workforce | 30 | on hold | 69,900 | 2026-12-07 |
| Riverbend | 54 | active | 72,250 | 2026-08-10 |

## Notes

- The dashboard seed (`seed-data.json`) is regenerated from this table by the build session.
- The weekly review compares the seed against this table and the project files under `projects/`.
