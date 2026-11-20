"""Validated, versioned run configuration."""

from ipaddress import ip_address, ip_network
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class Settings(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, allow_inf_nan=False, hide_input_in_errors=True
    )


class Detector(Settings):
    model: str | None = None
    readout: str | None = None
    manufacturer: str | None = None
    sensor: str | None = None
    monochrome: Literal[True] = True
    full_shape: tuple[int, int] | None = None
    pixel_um: float | None = Field(None, gt=0)
    output_bits: int | None = Field(None, gt=0)
    cooling: str | None = None
    gain_e_per_adu: float | None = Field(None, gt=0)
    read_noise_e: float | None = Field(None, ge=0)
    saturation: float | None = None
    linear_max: float | None = None
    evidence: str | None = None
    # Each assertion binds the characterization to observed detector settings.
    characterized_settings: dict[str, str | FiniteFloat] = Field(default_factory=dict)
    bad_pixels_yx: tuple[tuple[int, int], ...] = ()
    hot_pixels_yx: tuple[tuple[int, int], ...] = ()
    dead_pixels_yx: tuple[tuple[int, int], ...] = ()

    @model_validator(mode="after")
    def evidence_required(self):
        parameters = (self.gain_e_per_adu, self.read_noise_e, self.saturation, self.linear_max)
        if any(x is not None for x in parameters):
            keys = {
                "camera",
                "readout",
                "gain",
                "offset",
                "bin_x",
                "bin_y",
                "unit",
                "temperature_min_c",
                "temperature_max_c",
            }
            if not self.evidence or not keys.issubset(self.characterized_settings):
                raise ValueError(
                    "physical thresholds require measurement evidence and operating settings"
                )
            if float(self.characterized_settings["temperature_min_c"]) > float(
                self.characterized_settings["temperature_max_c"]
            ):
                raise ValueError("invalid characterization temperature range")
        if (
            self.linear_max is not None
            and self.saturation is not None
            and self.linear_max > self.saturation
        ):
            raise ValueError("linear_max must be at or below saturation")
        return self


class Calibration(Settings):
    bias_only_max_exposure_s: float | None = Field(None, gt=0)
    bias_only_evidence: str | None = None
    temperature_tolerance_c: float = Field(0, ge=0)
    temperature_evidence: str | None = None
    method: Literal["mean", "median", "clipped_mean"] = "mean"
    min_frames: int = Field(5, ge=3)
    clip_sigma: float = Field(4, gt=0)
    bootstrap_samples: int = Field(64, ge=32)
    flat_min_response: float = Field(0.1, gt=0, lt=1)
    flat_peak_code_fraction_max: float | None = Field(None, gt=0, lt=1)
    detector_keys: tuple[str, ...] = ()
    optical_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def conditions(self):
        if (self.bias_only_max_exposure_s is not None) != bool(
            self.bias_only_evidence and self.bias_only_evidence.strip()
        ):
            raise ValueError(
                "bias-only exposure limit and negligible-dark evidence are both required"
            )
        if self.temperature_tolerance_c and not self.temperature_evidence:
            raise ValueError("nonzero temperature tolerance requires supporting evidence")
        if self.method != "mean" and self.min_frames < 12:
            raise ValueError("robust bootstrap requires at least 12 frames")
        return self


class Quality(Settings):
    profile: Literal["GENERAL_SCIENCE", "PRECISION_PHOTOMETRY", "ASTROMETRY"] = "GENERAL_SCIENCE"
    threshold_sigma: float = Field(6, gt=0)
    detection_smoothing_sigma_px: float | None = Field(None, gt=0, le=12)
    box: int = Field(64, ge=8)
    fit_radius: int = Field(6, ge=3)
    max_sources: int = Field(500, ge=1)
    min_sources: int | None = Field(None, ge=1)
    max_fwhm_px: float | None = Field(None, gt=0)
    warn_fwhm_px: float | None = Field(None, gt=0)
    cosmic_candidate_sigma: float | None = Field(None, ge=5)
    max_ellipticity: float | None = Field(None, ge=0, lt=1)


Backend = Literal["astrometry_net", "ansvr", "ansvr_http", "local", "online", "auto"]
BACKENDS = ("astrometry_net", "ansvr", "ansvr_http", "local", "online", "auto")


class Online(Settings):
    endpoint: Literal["https://nova.astrometry.net"] = "https://nova.astrometry.net"
    timeout_s: float = Field(300, gt=0, le=3600)
    request_timeout_s: float = Field(20, gt=0, le=120)
    poll_s: float = Field(2, gt=0, le=60)
    retries: int = Field(3, ge=0, le=6)
    max_concurrent_jobs: int = Field(2, ge=1, le=8)
    max_sources: int = Field(300, ge=6, le=1000)
    max_image_mib: int = Field(48, ge=1, le=128)
    upload_mode: Literal["source_list", "image", "image_fallback"] = "source_list"
    publicly_visible: bool = False
    authorize_upload: bool = False
    authorize_image_upload: bool = False
    catalogue_independence_evidence: str | None = None


class Gaia(Settings):
    enabled: bool = False
    allow_network: bool = False
    cache_dir: Path | None = None
    g_limit: float = Field(18, gt=0, le=22)
    max_rows: int = Field(20000, ge=100, le=100000)
    max_radius_deg: float = Field(3, gt=0, le=10)
    pm_limit_mas_yr: float = Field(12000, gt=0, le=50000)
    timeout_s: float = Field(25, gt=0, le=120)


class Astrometry(Settings):
    backend: Backend = "astrometry_net"
    executable: str | None = None
    ansvr_root: Path | None = None
    ansvr_url: str | None = None
    allow_private_ansvr: bool = False
    backend_config: Path | None = None
    online: Online = Field(default_factory=lambda: Online.model_validate({}))
    fallback_enabled: bool = False
    index_manifest: Path | None = None
    catalogue: Path | None = None
    gaia: Gaia = Field(default_factory=lambda: Gaia.model_validate({}))
    catalogue_independence_evidence: str | None = None
    timeout_s: int = Field(120, ge=1)
    attempts: int = Field(1, ge=1, le=3)
    scale_min: float | None = Field(None, gt=0)
    scale_max: float | None = Field(None, gt=0)
    pointing_radius_deg: float | None = Field(None, gt=0, le=180)
    max_rms_arcsec: float | None = Field(None, gt=0)
    match_radius_arcsec: float = Field(5, gt=0)
    min_matches: int = Field(10, ge=3)
    min_match_fraction: float = Field(0.5, gt=0, le=1)
    min_coverage_fraction: float = Field(0.15, gt=0, le=1)
    max_outlier_fraction: float = Field(0.25, ge=0, lt=1)

    @model_validator(mode="after")
    def validate_scale(self):
        if self.backend == "ansvr" and (self.ansvr_root is None or self.executable is not None):
            raise ValueError("ANSVR requires ansvr_root and uses its bundled executable")
        if self.backend != "ansvr" and self.ansvr_root is not None:
            raise ValueError("ansvr_root requires the ansvr backend")
        if self.backend in ("ansvr_http", "local", "auto"):
            if (
                (self.backend == "ansvr_http" and not self.ansvr_url)
                or self.executable
                or self.backend_config
            ):
                raise ValueError("ANSVR HTTP requires ansvr_url and uses the service configuration")
            url = urlsplit(self.local_endpoint)
            host_ok = url.hostname in {"127.0.0.1", "::1"}
            if self.allow_private_ansvr and not host_ok and url.hostname:
                try:
                    address = ip_address(url.hostname)
                    host_ok = any(
                        address in ip_network(net)
                        for net in (
                            "10.0.0.0/8",
                            "172.16.0.0/12",
                            "192.168.0.0/16",
                            "fc00::/7",
                        )
                    )
                except ValueError:
                    pass
            if (
                url.scheme != "http"
                or not host_ok
                or url.username is not None
                or url.path not in ("", "/")
                or url.query
                or url.fragment
                or not url.port
            ):
                raise ValueError(
                    "ansvr_url must be a loopback or explicitly allowed private HTTP origin with an explicit port"
                )
        elif self.ansvr_url is not None and self.backend != "online":
            raise ValueError("ansvr_url requires an HTTP backend")
        if (self.scale_min is None) != (self.scale_max is None):
            raise ValueError("specify both pixel scale limits")
        if (
            self.scale_min is not None
            and self.scale_max is not None
            and self.scale_min >= self.scale_max
        ):
            raise ValueError("pixel scale limits are reversed")
        return self

    @property
    def local_endpoint(self) -> str:
        return self.ansvr_url or "http://127.0.0.1:8080"


def astrometry_override(
    settings: Astrometry,
    backend: str | None = None,
    *,
    allow_online: bool = False,
    allow_image: bool = False,
) -> Astrometry:
    """Apply CLI policy before calculating processing or batch identities."""
    values = settings.model_dump()
    if backend is not None and backend != settings.backend:
        values["backend"] = backend
        if backend in ("local", "online", "auto"):
            values.update(executable=None, ansvr_root=None, backend_config=None)
        elif backend in ("astrometry_net", "ansvr"):
            values["ansvr_url"] = None
    if allow_online:
        values["online"]["authorize_upload"] = True
    if allow_image:
        values["online"]["authorize_image_upload"] = True
    return Astrometry.model_validate(values)


class Config(Settings):
    schema_version: Literal[1] = 1
    node: str
    synthetic_test: bool = Field(False, strict=True)
    detector: Detector = Field(default_factory=lambda: Detector.model_validate({}))
    calibration: Calibration = Field(default_factory=lambda: Calibration.model_validate({}))
    photon_expectation: Path | None = None
    photon_expectation_evidence: str | None = None
    quality: Quality = Field(default_factory=lambda: Quality.model_validate({}))
    astrometry: Astrometry = Field(default_factory=lambda: Astrometry.model_validate({}))
    work_dir: Path = Path("osp-work")
    raw_dir: Path | None = None
    calibration_dir: Path | None = None
    workers: int = Field(1, ge=1)
    memory_mib: int = Field(1024, ge=16)
    max_input_mib: int = Field(1024, ge=1)
    worker_timeout_s: int = Field(900, ge=1)
    product_schema: Literal[1] = 1
    overrides: dict[str, str | FiniteFloat] = Field(default_factory=dict)

    @model_validator(mode="after")
    def override_names(self):
        from .ingest import FIELDS

        unknown = set(self.overrides) - FIELDS.keys()
        if unknown:
            raise ValueError(f"unsupported overrides: {sorted(unknown)}")
        if bool(self.photon_expectation) != bool(
            self.photon_expectation_evidence and self.photon_expectation_evidence.strip()
        ):
            raise ValueError(
                "independent photon expectation path and evidence must both be supplied"
            )
        return self


def load_config(path: Path) -> Config:
    """Read YAML and resolve relative paths against the configuration location."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    config = Config.model_validate(doc)
    base = path.resolve().parent
    sub = config.astrometry
    astrometry = sub.model_copy(
        update={
            key: base / value
            for key in ("catalogue", "backend_config", "ansvr_root", "index_manifest")
            if (value := getattr(sub, key)) is not None
        }
    )
    if sub.gaia.enabled or sub.gaia.cache_dir is not None:
        astrometry = astrometry.model_copy(
            update={
                "gaia": sub.gaia.model_copy(
                    update={
                        "cache_dir": base / (sub.gaia.cache_dir or config.work_dir / "gaia-cache")
                    }
                )
            }
        )
    return config.model_copy(
        update={
            **{
                key: base / value
                for key in ("work_dir", "raw_dir", "calibration_dir", "photon_expectation")
                if (value := getattr(config, key)) is not None
            },
            "astrometry": astrometry,
        }
    )
