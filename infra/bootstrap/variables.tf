# Inputs for the run-once state bootstrap. No value here is a secret; real values
# come from a git-ignored terraform.tfvars (see terraform.tfvars.example), and
# project_tag is injected from config via TF_VAR_project_tag by the Make targets.

variable "aws_region" {
  description = "AWS region for the remote-state bucket."
  type        = string
}

variable "state_bucket" {
  description = "Globally unique name for the versioned Terraform remote-state bucket."
  type        = string
}

variable "project_tag" {
  description = "Cost-allocation tag value, single-sourced from config.project_tag via TF_VAR_project_tag."
  type        = string
}
