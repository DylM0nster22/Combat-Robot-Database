#!/usr/bin/env python3
"""Fail CI on research-shape mistakes that can turn into unsafe recommendations."""

import json
import os
import sys
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESEARCH_DIR = os.path.join(ROOT, "data", "research")
MARKETPLACE_HOSTS = {
    "amazon.com", "www.amazon.com",
    "ebay.com", "www.ebay.com",
    "aliexpress.com", "www.aliexpress.com",
    "banggood.com", "www.banggood.com",
    "usa.banggood.com",
}


def http_sources(entity):
    return [
        s for s in entity.get("sources", [])
        if isinstance(s, str) and s.startswith(("http://", "https://"))
    ]


def main():
    errors = []
    warnings = []
    checked_files = 0
    checked_entities = 0

    for filename in sorted(os.listdir(RESEARCH_DIR)):
        if not filename.endswith(".json"):
            continue
        checked_files += 1
        path = os.path.join(RESEARCH_DIR, filename)
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{filename}: cannot parse: {exc}")
            continue

        seen = set()
        for entity in payload.get("entities", []):
            if not isinstance(entity, dict):
                errors.append(f"{filename}: non-object entity")
                continue
            checked_entities += 1
            entity_id = entity.get("id", "<missing-id>")
            if entity_id in seen:
                errors.append(f"{filename}: duplicate entity id {entity_id}")
            seen.add(entity_id)

            if entity.get("type") != "component":
                continue

            confidence = entity.get("confidence", "medium")
            reference_only = bool(entity.get("reference_only"))
            catalog_only = bool(entity.get("catalog_entry_only"))
            sources = http_sources(entity)

            if confidence == "low" and not reference_only:
                errors.append(
                    f"{filename}: {entity_id} is low-confidence but not reference_only"
                )
            if reference_only and catalog_only:
                errors.append(
                    f"{filename}: {entity_id} cannot be both reference_only and catalog_entry_only"
                )

            # High-confidence recommendation candidates need a real cited URL.
            # Generic standards/reference classes are allowed to rely on domain
            # knowledge because they are hidden from normal recommendation flows.
            if (
                confidence == "high"
                and not reference_only
                and not catalog_only
                and not sources
            ):
                errors.append(
                    f"{filename}: {entity_id} is a high-confidence exact component "
                    "with no cited URL"
                )

            # A marketplace listing can establish that a product exists, but by
            # itself it is not enough to call electrical/mechanical limits
            # manufacturer-verified.
            if confidence == "high" and sources and all(
                urlparse(s).netloc.lower() in MARKETPLACE_HOSTS for s in sources
            ):
                errors.append(
                    f"{filename}: {entity_id} is high-confidence from marketplace-only sources"
                )

            if entity.get("product_url") and not sources:
                warnings.append(
                    f"{filename}: {entity_id} has product_url but no cited source URL"
                )

    for warning in warnings:
        print("WARNING:", warning)
    for error in errors:
        print("ERROR:", error)

    print(
        f"audited {checked_entities} entities across {checked_files} research files; "
        f"{len(errors)} errors, {len(warnings)} warnings"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
