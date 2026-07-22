# Minimal public networking: one VPC, one public subnet, an internet gateway, and
# a default route. Deliberately NO NAT gateway (ADR-0003 cost trap): the instance
# sits in the public subnet with a tight security group, so it reaches the
# internet through the gateway without the per-hour NAT charge.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
}

# The availability zone is an input rather than an aws_availability_zones data
# source, so plan stays offline and credential-free (the same reason ami_id is a
# variable). Left null, AWS assigns a zone at apply; that is not safe here,
# because the Graviton instance types this stack runs are not offered in every
# zone of a region. An apply that landed on such a zone failed at RunInstances
# with "Unsupported: your requested instance type is not supported in your
# requested Availability Zone", after the subnet was already created. Pinning the
# zone in tfvars makes placement deterministic across re-applies rather than a
# one-in-six coin flip. Confirm a candidate zone offers the type with:
#   aws ec2 describe-instance-type-offerings --location-type availability-zone \
#     --filters Name=instance-type,Values=<instance_type> --query 'InstanceTypeOfferings[].Location'
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true
}

resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
}

resource "aws_route" "default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}
