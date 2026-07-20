output "instance_id" {
  description = "EC2 instance id of the compute box."
  value       = aws_instance.app.id
}

output "instance_public_ip" {
  description = "Auto-assigned public IPv4 of the compute box (reachable on the dashboard port from the owner IP only)."
  value       = aws_instance.app.public_ip
}
