#!/usr/bin/env python3
"""Tag-based teardown audit (AT-11, NFR-C2, ADR-0005).

After the ephemeral compute layer is destroyed, this queries for any resource
carrying the project tag that still bills by the hour, a running EC2 instance, a
NAT gateway, an attached or unattached public IPv4 (Elastic IP) address, or a
load balancer, and exits non-zero, naming the offenders, if any remain. A clean
teardown leaves none and the audit exits zero.

Region, the project tag, and the optional endpoint override all come from the
config object (the same override as the P2-T1 adapters), so this runs against the
moto server in tests and against real AWS in P2-T3 with no code change. It lives
under scripts/ (not core/) and touches boto3 only in the run path, so INV-4 and
AT-10 stay satisfied. It is also safe to run on a schedule as a backstop.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any

from climate_index.config import Settings, get_settings

# The cost-allocation tag key. Its value is single-sourced from config.project_tag
# (the same value Terraform applies via TF_VAR_project_tag), so the audit filter
# and the applied tags cannot drift.
PROJECT_TAG_KEY = "Project"

# NAT gateway states that still bill (a deleted or failed gateway does not).
_LIVE_NAT_STATES = ("pending", "available")

# EC2 instance states that still bill by the hour.
_BILLING_INSTANCE_STATES = ("pending", "running")


@dataclass(frozen=True)
class Offender:
    """A still-billing resource that carries the project tag."""

    kind: str
    identifier: str

    def __str__(self) -> str:
        return f"{self.kind} {self.identifier}"


def _client(settings: Settings, service: str) -> Any:
    """Build a boto3 client honoring the region and optional endpoint override."""
    import boto3

    return boto3.client(
        service,
        region_name=settings.aws_region,
        endpoint_url=settings.aws_endpoint_url,
    )


def _tagged(tags: list[dict[str, Any]], tag_value: str) -> bool:
    """True when the resource carries the project tag with the expected value."""
    return any(t.get("Key") == PROJECT_TAG_KEY and t.get("Value") == tag_value for t in tags)


def _find_instances(ec2: Any, tag_value: str) -> list[Offender]:
    response = ec2.describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": list(_BILLING_INSTANCE_STATES)}]
    )
    offenders: list[Offender] = []
    for reservation in response["Reservations"]:
        for instance in reservation["Instances"]:
            if _tagged(instance.get("Tags", []), tag_value):
                offenders.append(Offender("ec2-instance", instance["InstanceId"]))
    return offenders


def _find_nat_gateways(ec2: Any, tag_value: str) -> list[Offender]:
    response = ec2.describe_nat_gateways()
    offenders: list[Offender] = []
    for gateway in response["NatGateways"]:
        if gateway.get("State") in _LIVE_NAT_STATES and _tagged(gateway.get("Tags", []), tag_value):
            offenders.append(Offender("nat-gateway", gateway["NatGatewayId"]))
    return offenders


def _find_addresses(ec2: Any, tag_value: str) -> list[Offender]:
    response = ec2.describe_addresses()
    offenders: list[Offender] = []
    for address in response["Addresses"]:
        if _tagged(address.get("Tags", []), tag_value):
            identifier = address.get("PublicIp") or address.get("AllocationId") or "unknown"
            offenders.append(Offender("public-ipv4", identifier))
    return offenders


def _find_load_balancers(elbv2: Any, tag_value: str) -> list[Offender]:
    response = elbv2.describe_load_balancers()
    arns = [lb["LoadBalancerArn"] for lb in response["LoadBalancers"]]
    if not arns:
        return []
    offenders: list[Offender] = []
    described = elbv2.describe_tags(ResourceArns=arns)
    for description in described["TagDescriptions"]:
        if _tagged(description.get("Tags", []), tag_value):
            offenders.append(Offender("load-balancer", description["ResourceArn"]))
    return offenders


def find_billable_resources(settings: Settings) -> list[Offender]:
    """Return every still-billing resource carrying the project tag."""
    ec2 = _client(settings, "ec2")
    elbv2 = _client(settings, "elbv2")
    tag_value = settings.project_tag
    offenders: list[Offender] = []
    offenders.extend(_find_instances(ec2, tag_value))
    offenders.extend(_find_nat_gateways(ec2, tag_value))
    offenders.extend(_find_addresses(ec2, tag_value))
    offenders.extend(_find_load_balancers(elbv2, tag_value))
    return offenders


def main(argv: list[str] | None = None) -> int:
    settings = get_settings()
    if settings.aws_region is None:
        print("teardown audit: CII_AWS_REGION is not configured.", file=sys.stderr)
        return 2

    offenders = find_billable_resources(settings)
    if offenders:
        print(
            f"teardown audit FAILED: {len(offenders)} billable resource(s) still carry "
            f"the project tag '{settings.project_tag}':",
            file=sys.stderr,
        )
        for offender in offenders:
            print(f"  {offender}", file=sys.stderr)
        return 1

    print(
        f"teardown audit OK: no billable resource carries the project tag '{settings.project_tag}'."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
