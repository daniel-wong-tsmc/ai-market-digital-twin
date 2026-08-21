"""gpu_agent/pricepull.py — F122: pull GPU rental prices from public provider APIs into one
local daily snapshot CSV.

Providers (no account needed): Azure, AWS (via ec2.shop), RunPod, Vast.ai, CoreWeave.
Optional (needs a free API key in env LAMBDA_API_KEY): Lambda Labs.

Every price is one long-format row (SNAPSHOT_FIELDS). The snapshot folder is LOCAL ONLY
(gitignored under gpu_agent/data/). DISPLAY-ONLY downstream (F8): pricefeed/price_local read
these snapshots for the dashboard tile, brief price lines and rental series — never scoring.

No wall-clock here: `as_of` and `retrieved_at` are parameters; the CLI edge supplies them.
Ported 2026-08-20 from the user's standalone C:\\Users\\danie\\gpu-price-tracker\\pull_gpu_prices.py.
"""
from __future__ import annotations

import csv
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_SNAPSHOT_DIR = Path(__file__).parent / "data" / "leasing_snapshots"
UA = {"User-Agent": "Mozilla/5.0 (gpu-price-research script)"}
SNAPSHOT_FIELDS = ["provider", "gpu_model", "price_type", "usd_per_gpu_hr",
                   "usd_per_instance_hr", "gpus_per_instance", "instance", "region",
                   "source", "retrieved_at"]


def http_get(url, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def row(provider, gpu_model, price_type, per_gpu, per_instance, count, instance, region, source):
    """One normalized price row. `retrieved_at` is stamped later by run_pull."""
    return {
        "provider": provider,
        "gpu_model": gpu_model,
        "price_type": price_type,
        "usd_per_gpu_hr": round(per_gpu, 4) if per_gpu is not None else None,
        "usd_per_instance_hr": round(per_instance, 4) if per_instance is not None else None,
        "gpus_per_instance": count,
        "instance": instance,
        "region": region,
        "source": source,
        "retrieved_at": "",
    }


NORMALIZE_RULES = [
    (r"gb300", "GB300"), (r"gb200", "GB200"),
    (r"b300", "B300"), (r"b200", "B200"),
    (r"h200", "H200"),
    (r"h100.*nvl|nc40ads|nc80adis", "H100 NVL"),
    (r"h100", "H100"),
    (r"a100.*(80|amsr|nc24ads)|(80|amsr|nc24ads).*a100", "A100 80GB"),
    (r"a100", "A100 40GB"),
    (r"mi300x", "MI300X"), (r"mi325x", "MI325X"),
    (r"l40s", "L40S"), (r"l40\b", "L40"), (r"l4\b", "L4"),
    (r"a10g", "A10G"), (r"a10\b", "A10"), (r"a40\b", "A40"),
    (r"rtx ?pro ?6000", "RTX PRO 6000"),
    (r"6000 ?ada", "RTX 6000 Ada"),
    (r"5090", "RTX 5090"), (r"4090", "RTX 4090"), (r"3090", "RTX 3090"),
    (r"v100", "V100"), (r"\bt4\b", "T4"),
]


def normalize(name):
    low = name.lower()
    for pat, canon in NORMALIZE_RULES:
        if re.search(pat, low):
            return canon
    return name.strip()


# ---------------------------------------------------------------- Azure
AZURE_SKUS = {
    # armSkuName: (gpu count, model hint)
    "Standard_NC40ads_H100_v5": (1, "H100 NVL"),
    "Standard_NC80adis_H100_v5": (2, "H100 NVL"),
    "Standard_ND96isr_H100_v5": (8, "H100"),
    "Standard_ND96isr_H200_v5": (8, "H200"),
    "Standard_ND96amsr_A100_v4": (8, "A100 80GB"),
    "Standard_NC24ads_A100_v4": (1, "A100 80GB"),
}

HOURS_PER_YEAR = 8760


def fetch_azure():
    rows = []
    for sku, (count, model) in AZURE_SKUS.items():
        flt = f"armSkuName eq '{sku}'"
        url = ("https://prices.azure.com/api/retail/prices?$filter="
               + urllib.parse.quote(flt))
        items = []
        while url:  # results are paginated
            page = json.loads(http_get(url))
            items.extend(page.get("Items", []))
            url = page.get("NextPageLink")
        for i in items:
            priced = azure_item_to_price(i)
            if not priced:
                continue
            ptype, hourly = priced
            rows.append(row("Azure", model, ptype, hourly / count, hourly, count,
                            sku, i["armRegionName"], "prices.azure.com"))
    return rows


def azure_item_to_price(item):
    """One Azure price-list item -> (price_type, usd_per_hour), or None to skip."""
    if "Windows" in item["productName"] or "Low Priority" in item["meterName"]:
        return None
    if item["retailPrice"] <= 0:
        return None
    if item["type"] == "Consumption":
        ptype = "spot" if "Spot" in item["meterName"] else "on_demand"
        return ptype, item["retailPrice"]
    if item["type"] == "Reservation":
        # reservations are quoted as one lump sum for the whole term
        years = {"1 Year": 1, "3 Years": 3, "5 Years": 5}.get(item.get("reservationTerm"))
        if not years:
            return None
        return f"reserved_{years}yr", item["retailPrice"] / (years * HOURS_PER_YEAR)
    return None


# ---------------------------------------------------------------- AWS (via ec2.shop)
AWS_FAMILIES = {
    # filter: {instance prefix: (gpu count, model)}
    "p4d": {"p4d.24xlarge": (8, "A100 40GB")},
    "p4de": {"p4de.24xlarge": (8, "A100 80GB")},
    # ec2.shop does not list p6 (B200) or p5e in any region as of Aug 2026
    "p5": {"p5.48xlarge": (8, "H100"), "p5en.48xlarge": (8, "H200")},
    "g6e": {"g6e.xlarge": (1, "L40S")},
}


AWS_REGIONS = ["us-east-1", "us-east-2", "us-west-2", "eu-west-1", "ap-northeast-1"]


def fetch_aws():
    rows = []
    for region in AWS_REGIONS:
        for fam, mapping in AWS_FAMILIES.items():
            data = json.loads(http_get(f"https://ec2.shop?region={region}&filter={fam}",
                                       headers={"accept": "json"}))
            for p in data.get("Prices", []):
                inst = p["InstanceType"]
                if inst not in mapping:
                    continue
                count, model = mapping[inst]
                terms = [("on_demand", p["Cost"]), ("spot", p.get("SpotPrice")),
                         ("reserved_1yr", p.get("Reserved1yPrice")),
                         ("reserved_3yr", p.get("Reserved3yPrice"))]
                for ptype, raw in terms:
                    try:
                        price = float(raw)
                    except (ValueError, TypeError):
                        continue
                    if price > 0:
                        rows.append(row("AWS", model, ptype, price / count, price,
                                        count, inst, region, "ec2.shop"))
    return rows


# ---------------------------------------------------------------- RunPod
def fetch_runpod():
    q = {"query": "query { gpuTypes { id displayName memoryInGb securePrice communityPrice } }"}
    data = json.loads(http_get("https://api.runpod.io/graphql",
                               headers={"Content-Type": "application/json"},
                               data=json.dumps(q).encode()))
    rows = []
    for g in data["data"]["gpuTypes"]:
        model = normalize(g["id"])
        for field, label in (("securePrice", "on_demand"), ("communityPrice", "community")):
            price = g.get(field)
            if price:
                rows.append(row("RunPod", model, label, price, price, 1,
                                g["displayName"], "global", "api.runpod.io"))
    return rows


# ---------------------------------------------------------------- Vast.ai
VAST_MODELS = ["H100 SXM", "H100 NVL", "H200", "B200", "A100 SXM4", "RTX 4090", "RTX 5090", "MI300X"]


def fetch_vast():
    rows = []
    for model in VAST_MODELS:
        for count in (1, 2, 4, 8):
            q = {
                "gpu_name": {"eq": model}, "num_gpus": {"eq": count},
                "rentable": {"eq": True}, "verified": {"eq": True},
                "order": [["dph_total", "asc"]], "limit": 20,
            }
            url = ("https://console.vast.ai/api/v0/bundles/?q="
                   + urllib.parse.quote(json.dumps(q)))
            offers = json.loads(http_get(url)).get("offers", [])
            picked = pick_vast_offer(offers)
            if not picked:
                continue
            per_gpu, best = picked
            rows.append(row("Vast.ai", normalize(model), "marketplace_min",
                            per_gpu, per_gpu * count, count, f"{count}x {model}",
                            best.get("geolocation", ""), "console.vast.ai"))
            # interruptible: you bid, and can be kicked when outbid; min_bid
            # is the bid that would win the cheapest machine right now
            bid = best.get("min_bid")
            if bid:
                rows.append(row("Vast.ai", normalize(model), "interruptible_min",
                                bid / count, bid, count, f"{count}x {model}",
                                best.get("geolocation", ""), "console.vast.ai"))
    return rows


def pick_vast_offer(offers):
    """Cheapest per-GPU offer -> (usd_per_gpu_hr, offer), or None.

    gpu_frac is the fraction of the host machine (1 of N GPUs), so
    dph_total already prices num_gpus whole GPUs.
    """
    cands = [(o["dph_total"] / o["num_gpus"], o) for o in offers
             if o.get("dph_total") and o.get("num_gpus")]
    if not cands:
        return None
    return min(cands, key=lambda c: c[0])


# ---------------------------------------------------------------- CoreWeave (HTML scrape)
def fetch_coreweave():
    return parse_coreweave(http_get("https://www.coreweave.com/pricing"))


def parse_coreweave(html):
    rows, seen = [], set()
    blocks = re.split(r'table-model-name">', html)[1:]
    for b in blocks:
        name = b.split("<")[0].strip()
        # each model appears twice (desktop + mobile layout); only one copy
        # of the block carries prices, so dedupe only after a successful parse
        od = re.search(r"On-Demand Price:.*?\$([\d,]+\.\d+)", b, re.S)
        sp = re.search(r"Spot Price:.*?\$([\d,]+\.\d+)", b, re.S)
        meta = re.search(r'table-meta-value[^>]*>([\d,]+)<', b)
        if name in seen or not od or not meta:
            continue
        seen.add(name)
        count = int(meta.group(1).replace(",", ""))
        if count < 1 or count > 72:
            continue
        model = normalize(name)
        for m, label in ((od, "on_demand"), (sp, "spot")):
            if m:
                price = float(m.group(1).replace(",", ""))
                rows.append(row("CoreWeave", model, label, price / count, price,
                                count, name, "us", "coreweave.com/pricing"))
    return rows


# ---------------------------------------------------------------- Lambda Labs (optional)
def fetch_lambda():
    key = os.environ.get("LAMBDA_API_KEY")
    if not key:
        return []
    data = json.loads(http_get("https://cloud.lambdalabs.com/api/v1/instance-types",
                               headers={"Authorization": f"Bearer {key}"}))
    rows = []
    for name, info in data["data"].items():
        it = info["instance_type"]
        specs = it["specs"]
        count = specs.get("gpus", 1) or 1
        price = it["price_cents_per_hour"] / 100
        rows.append(row("Lambda", normalize(it["description"]), "on_demand",
                        price / count, price, count, name, "varies", "cloud.lambdalabs.com"))
    return rows


# ---------------------------------------------------------------- main
FETCHERS = [
    ("Azure", fetch_azure), ("AWS", fetch_aws), ("RunPod", fetch_runpod),
    ("Vast.ai", fetch_vast), ("CoreWeave", fetch_coreweave), ("Lambda", fetch_lambda),
]


# ---------------------------------------------------------------- snapshot I/O
def snapshot_path(out_dir, as_of: str) -> Path:
    """The one CSV for a cycle day: <out_dir>/gpu_prices-<YYYY-MM-DD>.csv."""
    return Path(out_dir) / f"gpu_prices-{as_of}.csv"


def write_snapshot(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
        w.writeheader()
        w.writerows(rows)


def run_pull(as_of: str, out_dir, *, fetchers=None, retrieved_at: str = "") -> dict:
    """Run every fetcher, stamp rows, write ONE dated CSV (overwriting a same-day file).

    Never raises for a provider problem: each fetcher is isolated and a failure lands in
    `failed`. Zero rows -> no file is written and `path` is None. Returns the summary the
    CLI prints and the cycle log records."""
    fetchers = FETCHERS if fetchers is None else fetchers
    all_rows, failed, per_provider = [], [], {}
    for name, fn in fetchers:
        try:
            got = fn()
        except Exception as e:            # provider-level isolation, by design
            failed.append({"provider": name, "error": f"{type(e).__name__}: {e}"})
            continue
        for r in got:
            r["retrieved_at"] = retrieved_at
        all_rows.extend(got)
        per_provider[name] = len(got)
    all_rows.sort(key=lambda r: (r["gpu_model"], r["usd_per_gpu_hr"] or 0))
    path = None
    if all_rows:
        path = snapshot_path(out_dir, as_of)
        write_snapshot(path, all_rows)
    return {"date": as_of, "path": str(path) if path else None, "rows": len(all_rows),
            "perProvider": per_provider, "failed": failed}
