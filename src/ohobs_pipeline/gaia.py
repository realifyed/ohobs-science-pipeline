"""Bounded public Gaia DR3 TAP cone queries and immutable offline cache."""

import http.client
import io
import math
import ssl
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
from astropy.io.votable import parse

from .config import Gaia
from .integrity import digest, identity, publish_directory, read_json, write_json

HOST = "gea.esac.esa.int"
PATH = "/tap-server/tap/sync"
RELEASE = "Gaia DR3"
COLUMNS = (
    "source_id",
    "ra",
    "dec",
    "pmra",
    "pmdec",
    "ref_epoch",
    "ruwe",
    "duplicated_source",
    "phot_g_mean_mag",
)


class GaiaError(ValueError):
    """Gaia reference unavailable or unsuitable for verification."""


def _download(adql: str, settings: Gaia) -> bytes:
    payload = urlencode(
        {
            "REQUEST": "doQuery",
            "LANG": "ADQL",
            "FORMAT": "votable",
            "MAXREC": settings.max_rows + 1,
            "QUERY": adql,
        }
    ).encode("ascii")
    connection = http.client.HTTPSConnection(
        HOST, timeout=settings.timeout_s, context=ssl.create_default_context()
    )
    try:
        connection.request(
            "POST", PATH, payload, {"Content-Type": "application/x-www-form-urlencoded"}
        )
        with connection.getresponse() as response:
            if response.status != 200:
                raise GaiaError(f"Gaia TAP returned HTTP {response.status}")
            limit = 32 * 1024**2
            data = response.read(limit + 1)
            if len(data) > limit:
                raise GaiaError("Gaia TAP response exceeds the 32 MiB limit")
            return data
    except (OSError, http.client.HTTPException) as exc:
        raise GaiaError(f"Gaia TAP connection failed ({type(exc).__name__})") from None
    finally:
        connection.close()


def cone(wcs, shape: tuple[int, int], epoch, settings: Gaia) -> tuple[float, float, float]:
    """Enclose the sampled detector perimeter and configured motion envelope."""
    h, w = shape
    x = np.linspace(-0.5, w - 0.5, 33)
    y = np.linspace(-0.5, h - 0.5, 33)
    perimeter = wcs.pixel_to_world(
        np.concatenate((x, x, np.full_like(y, x[0]), np.full_like(y, x[-1]))),
        np.concatenate((np.full_like(x, y[0]), np.full_like(x, y[-1]), y, y)),
    ).icrs
    center = wcs.pixel_to_world((w - 1) / 2, (h - 1) / 2).icrs
    motion = settings.pm_limit_mas_yr * abs(epoch.tcb.jyear - 2016.0) / 3_600_000
    radius = math.ceil((float(np.max(center.separation(perimeter).deg)) + motion + 0.03) * 20) / 20
    if not 0 < radius <= settings.max_radius_deg:
        raise GaiaError("WCS footprint exceeds the configured Gaia cone limit")
    return round(float(center.ra.deg), 3) % 360, round(float(center.dec.deg), 3), radius


def reference(wcs, shape: tuple[int, int], epoch, settings: Gaia, root: Path) -> tuple[Path, dict]:
    """Return a checksummed ECSV and exact query provenance. Cache hits are offline."""
    ra, dec, radius = cone(wcs, shape, epoch, settings)
    query = (
        f"SELECT TOP {settings.max_rows + 1} {', '.join(COLUMNS)} FROM gaiadr3.gaia_source "
        f"WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.3f}, {dec:.3f}, {radius:.3f})) "
        f"AND phot_g_mean_mag <= {settings.g_limit:.6f} AND ruwe < 1.4 "
        f"AND pmra IS NOT NULL AND pmdec IS NOT NULL "
        f"AND POWER(pmra,2)+POWER(pmdec,2) <= {settings.pm_limit_mas_yr**2:.3f} "
        "ORDER BY phot_g_mean_mag, source_id"
    )
    key = identity({"schema": 1, "endpoint": HOST + PATH, "query": query})
    target = root / key
    cache = target / "reference.ecsv"
    manifest = target / "manifest.json"

    if not target.exists():
        if not settings.allow_network:
            raise GaiaError("Gaia reference absent from the offline cache; network is disabled")
        payload = _download(query, settings)
        if b"<!doctype" in payload.lower() or b"<!entity" in payload.lower():
            raise GaiaError("Gaia VOTable contains disallowed XML declarations")
        try:
            document = parse(io.BytesIO(payload), verify="exception")
            infos = list(document.infos)
            resources = list(document.resources)
            while resources:
                resource = resources.pop()
                infos.extend(resource.infos)
                resources.extend(resource.resources)
            if any(info.name == "QUERY_STATUS" and info.value != "OK" for info in infos):
                raise GaiaError("Gaia TAP query failed or was truncated")
            table = document.get_first_table().to_table()
            if not set(COLUMNS).issubset(table.colnames) or not 0 < len(table) <= settings.max_rows:
                raise GaiaError("Gaia TAP returned empty, incomplete, or row-limited data")
        except GaiaError:
            raise
        except (ValueError, OSError, StopIteration, IndexError) as exc:
            raise GaiaError("Gaia TAP returned an invalid VOTable") from exc
        with publish_directory(target) as temporary:
            table[list(COLUMNS)].write(temporary / "reference.ecsv", format="ascii.ecsv")
            write_json(
                temporary / "manifest.json",
                {
                    "id": key,
                    "release": RELEASE,
                    "endpoint": "https://" + HOST + PATH,
                    "query": query,
                    "center_ra_deg": ra,
                    "center_dec_deg": dec,
                    "radius_deg": radius,
                    "rows": len(table),
                    "sha256": digest(temporary / "reference.ecsv"),
                },
            )
    record = read_json(manifest)
    if record["id"] != key or record["query"] != query or digest(cache) != record["sha256"]:
        raise GaiaError("Gaia cache failed checksum or query identity verification")
    return cache, record
