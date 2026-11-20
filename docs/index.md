# OSP documentation

OSP 0.1.0rc2 reduces monochrome astronomical FITS with conservative calibration
matching and explicit scientific status. Begin with installation and the offline
fixture before using observational data.

| Topic | Guide |
| --- | --- |
| Installation | [Windows](installation/WINDOWS.md), [Linux](installation/linux.md), [source and distributions](installation/from-source.md), [troubleshooting](installation/troubleshooting.md) |
| First use | [Offline quickstart](getting-started/quickstart.md), [first observational reduction](getting-started/first-reduction.md) |
| Configuration | [Observatory and detector](user-guide/configuration.md), [complete schema](api/configuration-schema.json), [astrometry settings](configuration.md) |
| Processing | [Ingestion](user-guide/fits-ingestion.md), [calibration](user-guide/calibration.md), [QC](user-guide/quality-assessment.md), [astrometry](user-guide/astrometry.md) |
| Operation | [Batch jobs](user-guide/batch-processing.md), [products](user-guide/data-products.md), [reporting](user-guide/reporting.md), [recovery](installation/operations.md) |
| Interfaces | [CLI](cli-reference.md), [Python](api/PUBLIC.md) |
| Science | [Calibration and uncertainty](science/calibration-methodology.md), [limitations](science/assumptions-and-limitations.md), [references](science/references.md) |
| Development | [Setup](developer-guide/development-setup.md), [architecture](developer-guide/architecture.md), [testing](developer-guide/testing.md), [contribution policy](../CONTRIBUTING.md) |
| Simulation | [Separate simulator tutorial](getting-started/SYNTHETIC.md), [origin policy](installation/SIMULATION-MIGRATION.md) |
| Evidence | [Current verification](validation/repository-improvements.md), [historical status](validation/RELEASE_STATUS.md), [OHOBS commissioning](commissioning/RELEASE_READINESS.md) |

Commissioning records describe one observatory and historical tests. Their
instrument parameters are not general defaults. Synthetic tests do not
establish real detector accuracy or on-sky astrometric performance.
