# Minimal public networking: one VPC, one public subnet, an internet gateway, and
# a default route. Deliberately NO NAT gateway (ADR-0003 cost trap): the instance
# sits in the public subnet with a tight security group, so it reaches the
# internet through the gateway without the per-hour NAT charge.

resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
}

# No availability_zone is set so no aws_availability_zones data source is needed;
# AWS assigns one at apply, keeping plan offline.
resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = var.subnet_cidr
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
