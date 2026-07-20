"""AT-11 teardown audit against the moto server (no spend).

Creates tagged resources across all four billing categories the audit queries, an
EC2 instance, a public IPv4 (Elastic IP), a NAT gateway, and a load balancer,
then asserts the audit finds and names every one. After tearing them down it
asserts the audit reports clean, which is the real post-destroy check AT-11 runs
in P2-T3. Reuses the session moto server from conftest.

The moto server is session-scoped and shared, so each test tags its resources
with a unique project tag (from the conftest resource counter). The audit filters
on that tag, so one test never sees another test's resources.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from climate_index.config import Settings

# scripts/ is on the pytest pythonpath, so the audit under test imports directly.
from teardown_audit import Offender, find_billable_resources

_REGION = "us-east-1"


def _settings(endpoint: str, tag: str) -> Settings:
    return Settings(aws_region=_REGION, aws_endpoint_url=endpoint, project_tag=tag)


def _client(endpoint: str, service: str) -> Any:
    import boto3

    return boto3.client(service, region_name=_REGION, endpoint_url=endpoint)


def _amazon_ami(ec2: Any) -> str:
    images = ec2.describe_images(Owners=["amazon"])["Images"]
    assert images, "moto returned no default AMIs to launch from"
    return str(images[0]["ImageId"])


@pytest.fixture()
def billable_estate(moto_endpoint: str, _resource_counter: Any) -> Any:
    """Stand up one tagged resource of each billing category, yield their ids."""
    tag = f"climate-index-audit-{next(_resource_counter)}"
    tags = [{"Key": "Project", "Value": tag}]
    ec2 = _client(moto_endpoint, "ec2")
    elbv2 = _client(moto_endpoint, "elbv2")

    vpc_id = ec2.create_vpc(CidrBlock="10.9.0.0/16")["Vpc"]["VpcId"]
    subnet_a = ec2.create_subnet(
        VpcId=vpc_id, CidrBlock="10.9.1.0/24", AvailabilityZone=f"{_REGION}a"
    )["Subnet"]["SubnetId"]
    subnet_b = ec2.create_subnet(
        VpcId=vpc_id, CidrBlock="10.9.2.0/24", AvailabilityZone=f"{_REGION}b"
    )["Subnet"]["SubnetId"]
    security_group = ec2.create_security_group(
        GroupName=f"{tag}-sg", Description="audit test", VpcId=vpc_id
    )["GroupId"]

    # Running EC2 instance (tagged).
    instance_id = ec2.run_instances(
        ImageId=_amazon_ami(ec2),
        InstanceType="t3.micro",
        MinCount=1,
        MaxCount=1,
        SubnetId=subnet_a,
        TagSpecifications=[{"ResourceType": "instance", "Tags": tags}],
    )["Instances"][0]["InstanceId"]

    # Standalone public IPv4 / Elastic IP (tagged).
    standalone_eip = ec2.allocate_address(Domain="vpc")["AllocationId"]
    ec2.create_tags(Resources=[standalone_eip], Tags=tags)

    # NAT gateway (tagged); its backing EIP is left untagged so only the gateway
    # itself is an offender.
    nat_eip = ec2.allocate_address(Domain="vpc")["AllocationId"]
    nat_id = ec2.create_nat_gateway(SubnetId=subnet_a, AllocationId=nat_eip)["NatGateway"][
        "NatGatewayId"
    ]
    ec2.create_tags(Resources=[nat_id], Tags=tags)

    # Application load balancer across the two subnets (tagged).
    lb_arn = elbv2.create_load_balancer(
        Name=f"{tag}-lb"[:32],
        Subnets=[subnet_a, subnet_b],
        SecurityGroups=[security_group],
        Type="application",
        Scheme="internet-facing",
        Tags=tags,
    )["LoadBalancers"][0]["LoadBalancerArn"]

    estate = {
        "ec2": ec2,
        "elbv2": elbv2,
        "tag": tag,
        "instance_id": instance_id,
        "standalone_eip": standalone_eip,
        "nat_id": nat_id,
        "lb_arn": lb_arn,
    }
    yield estate

    # Best-effort cleanup so a failing assertion does not leak an allocated EIP.
    with contextlib.suppress(Exception):
        ec2.release_address(AllocationId=standalone_eip)


def test_audit_finds_all_billable_categories(moto_endpoint: str, billable_estate: Any) -> None:
    offenders = find_billable_resources(_settings(moto_endpoint, billable_estate["tag"]))
    kinds = {offender.kind for offender in offenders}
    assert kinds == {"ec2-instance", "nat-gateway", "public-ipv4", "load-balancer"}, offenders

    identifiers = {offender.identifier for offender in offenders}
    assert billable_estate["instance_id"] in identifiers
    assert billable_estate["nat_id"] in identifiers
    assert billable_estate["lb_arn"] in identifiers


def test_audit_reports_clean_after_teardown(moto_endpoint: str, billable_estate: Any) -> None:
    ec2 = billable_estate["ec2"]
    elbv2 = billable_estate["elbv2"]

    ec2.terminate_instances(InstanceIds=[billable_estate["instance_id"]])
    ec2.delete_nat_gateway(NatGatewayId=billable_estate["nat_id"])
    ec2.release_address(AllocationId=billable_estate["standalone_eip"])
    elbv2.delete_load_balancer(LoadBalancerArn=billable_estate["lb_arn"])

    offenders: list[Offender] = find_billable_resources(
        _settings(moto_endpoint, billable_estate["tag"])
    )
    assert offenders == [], f"teardown should leave no tagged billable resource: {offenders}"
