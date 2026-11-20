# Architecture

The src/ohobs_pipeline package contains Core; packages/osp-sim/src/ohobs_sim is
the separately distributed synthetic generator. Both use setuptools and expose
their own console entry points. Core does not import or depend on the simulator.

Ingestion normalizes strict FITS metadata and checks input integrity. Masters
combine compatible calibrators and persist definitions and lineage. Reduction
applies detector correction, variance and DQ propagation. Pipeline orchestrates
calibration, quality and astrometry, then atomically publishes product directories.
Products validate FITS layout and provenance. Reporting consumes that evidence.

Jobs discover inputs, checkpoint in SQLite and dispatch isolated CLI workers.
Astrometry adapters cover native solve-field, ANSVR Cygwin, ANSVR-compatible
HTTP and Nova. Gaia provides optional explicit network/cache reference access.
Configuration uses frozen Pydantic models with forbidden unknown fields.

See [operations](../operations.md) for public entry points and processing states.
Scientific changes require numerical regression evidence and documented model
assumptions; a documentation change should not alter numerical algorithms.
