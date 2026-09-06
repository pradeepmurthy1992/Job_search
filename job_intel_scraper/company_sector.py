"""
Automotive-sector classification for the dashboard's "automotive only"
filter.

This is deliberately a curated table, not a keyword scan over the JD text:
every board in config.py was already individually researched (see
README's "Verified target companies"), so the real answer is already
known — guessing again from keywords would be strictly worse than what's
already been established. A company genuinely making or directly
supplying vehicles (OEM, Tier-1 automotive supplier, vehicle
manufacturer) counts as automotive; EV-CHARGING infrastructure, battery
manufacturing that isn't vehicle-specific, general precision
manufacturing, mining, data-centres, and infrastructure consultancies do
NOT — even though several of those were deliberately added under the
"adjacent sector" domain-expansion (see config.py's AU/NL/VN comments),
being adjacent is exactly what this filter is for excluding.

Unrecognized companies (a future scrape target not yet classified here,
or a manually-pasted job) fall back to a conservative keyword check —
default is NOT automotive unless the text gives a real signal, matching
the "never guess positive" pattern already used in eligibility.py and
salary.py.
"""

from __future__ import annotations

import re

# Keyed by board_or_company as it appears in config.py (case-insensitive
# match), or by company_name for manually-pasted jobs. True = genuinely
# automotive (OEM / Tier-1 supplier / vehicle manufacturer).
_KNOWN_COMPANY_SECTOR: dict[str, bool] = {
    # Automotive (OEM / Tier-1 / vehicle manufacturer)
    "onemobility": True,                    # automotive sensor/connectivity/electrification (VN)
    "one mobility group": True,
    "autocraft-solutions-group": True,      # EV battery remanufacturing for vehicles (NL) — "industry":"Automotive" per its own API
    "autocraft solutions group": True,
    "applied-ev": True,                     # autonomous/electric commercial-vehicle platform maker (AU)
    "applied ev": True,
    "zoomo": True,                          # light-EV (e-bike/scooter) manufacturer for last-mile delivery (AU)
    "lucidmotors": True,                    # EV OEM, genuinely manufactures vehicles (US)
    "lucid motors": True,
    "ineos-automotive": True,               # Grenadier 4x4 OEM (GB/DE)
    "ineos automotive": True,

    # Adjacent, NOT automotive (EV charging infra, battery mfg, general
    # manufacturing, mining, infrastructure, data-centres) — deliberately
    # excluded from this filter even though they're legitimately in
    # config.py under the sector-expansion reasoning.
    "axon": False,                          # public-safety hardware (VN)
    "uei": False,                           # consumer-electronics manufacturer (VN)
    "chargepoint": False,                   # EV charging infrastructure (NL)
    "fastned": False,                       # EV charging infrastructure (NL)
    "greenflux": False,                     # EV charge-point SaaS (NL)
    "enecoemobility": False,                # EV charging (NL)
    "eneco emobility": False,
    "nts": False,                           # precision manufacturing — semiconductor/life-sciences/defense (NL)
    "nts group": False,
    "rocsys": False,                        # robotic EV/truck charging automation, not vehicle mfg (NL)
    "leydenjar": False,                     # battery manufacturing, not vehicle-specific (NL)
    "leydenjar technologies": False,
    "milence": False,                       # EV truck charging network (NL)
    "allego": False,                        # EV charging infrastructure (NL)
    "airtrunk": False,                      # hyperscale data-centre developer (AU)
    "bradken": False,                       # mining/heavy-equipment wear parts (AU)
    "emesent": False,                       # autonomous mining-drone tech (AU)
    "relectrify": False,                    # battery-storage scale-up (AU)
    "waymo": False,                         # autonomous-driving tech integrated into vehicles built by others — doesn't manufacture vehicles itself (US/GB)
    "flyzipline": False,                    # drone logistics/hardware, not vehicles (US)
    "zipline": False,
    "kodiak": False,                        # autonomous-trucking tech, retrofits trucks built by others, not a manufacturer (US)
    "samsara": False,                       # IoT/fleet-management hardware, not vehicle manufacturing (US)
    "archer56": False,                      # eVTOL/aerospace manufacturer — aviation, not automotive (US)
    "archer aviation": False,
    "redwoodmaterials": False,              # battery/critical-materials manufacturing, not vehicle-specific (US)
    "redwood materials": False,
    "group14": False,                       # silicon battery tech, not vehicle-specific (US)
    "group14 technologies": False,
    "freenow": False,                       # mobility/ride-hailing app (BMW/Mercedes JV) — a service, not a vehicle manufacturer (DE)
    "freenow by lyft": False,
    "aldar": False,                         # real-estate/infrastructure developer, not automotive at all (AE)
    "aldar properties": False,
    "finn": False,                          # car-subscription/fleet-management service, not a vehicle manufacturer (DE)
    "instagrid": False,                     # portable battery/energy-storage manufacturer, not vehicle-specific (DE)
    "weride": True,                         # autonomous driving/robotaxi vehicle developer (SG)
    "wayve": True,                          # autonomous driving vehicle developer (GB)
    "formlabs": False,                      # 3D printing/additive manufacturing hardware, not vehicle-specific (VN/US)
    "ai71jobs": True,                       # autonomous racing vehicle/AI developer (AE)
    "nuro": True,                           # autonomous delivery vehicle manufacturer (US)
    "motional": True,                       # autonomous vehicle developer, Aptiv/Hyundai JV (US)
    "solidpower": False,                    # solid-state battery manufacturing, not vehicle-specific (US)
    "solid power": False,
    "silananotechnologies": False,          # battery materials, not vehicle-specific (US)
    "sila nanotechnologies": False,
    "faradayfuture": True,                  # EV manufacturer (US)
    "faraday future": True,
    "maymobility": True,                    # autonomous shuttle vehicle operator (US)
    "may mobility": True,
    "scoutmotors": True,                    # Volkswagen Group's US truck OEM brand (US)
    "scout motors": True,
    "gotion": False,                        # EV battery gigafactory, not vehicle-specific (US)
    "zoox": True,                           # autonomous robotaxi manufacturer, Amazon-owned (US)
    "aeva": False,                          # lidar/sensing hardware supplier, not vehicle-specific (US)
}

# Conservative fallback for anything not in the table above (manual
# entries, future scrape targets) — requires an explicit automotive/
# vehicle-manufacturing signal, not just "EV" or "electric" alone (those
# match plenty of charging-infrastructure and battery companies that
# aren't automotive by this filter's definition).
_AUTOMOTIVE_FALLBACK_PATTERN = re.compile(
    r"\b(automotive|vehicle manufactur|car manufactur|truck manufactur|"
    r"oem\b|tier[\s-]?1 (automotive )?supplier|automaker)\b",
    re.IGNORECASE,
)


def is_automotive(board_or_company: str, company_name: str = "", text: str = "") -> bool:
    """True if this job's company is genuinely automotive (OEM/Tier-1/
    vehicle manufacturer), for the dashboard's "automotive only" filter.
    Checks the curated table first (by board slug, then by company name);
    falls back to a conservative keyword check against title+description
    for anything not yet classified — defaulting to False, not a guess."""
    for key in (board_or_company, company_name):
        if key and key.strip().lower() in _KNOWN_COMPANY_SECTOR:
            return _KNOWN_COMPANY_SECTOR[key.strip().lower()]

    combined = f"{company_name} {text}"
    return bool(_AUTOMOTIVE_FALLBACK_PATTERN.search(combined))
