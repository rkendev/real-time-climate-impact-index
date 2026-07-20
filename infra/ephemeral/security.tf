# Tight security group: the dashboard port is reachable only from the owner IP,
# and there is no SSH ingress at all. Operator shell access is via SSM Session
# Manager (the processor role carries AmazonSSMManagedInstanceCore), so port 22
# stays closed.
resource "aws_security_group" "instance" {
  name_prefix = "${var.project_tag}-instance-"
  description = "Dashboard ingress from the owner IP only; all egress. No SSH (SSM provides shell)."
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Dashboard port, owner IP only"
    from_port   = var.dashboard_port
    to_port     = var.dashboard_port
    protocol    = "tcp"
    cidr_blocks = [var.owner_ip]
  }

  egress {
    description = "All egress (public subnet, no NAT gateway)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  lifecycle {
    create_before_destroy = true
  }
}
