variable "retired_aws_acknowledgement" {
  description = "Explicit acknowledgement required to inspect or clean up this retired AWS stack."
  type        = bool
  default     = false

  validation {
    condition     = var.retired_aws_acknowledgement
    error_message = "This AWS stack is retired. Use terraform_gcp; set retired_aws_acknowledgement=true only to manage existing legacy resources."
  }
}
