# Credentials. Get all four from the OCI console: Profile > User Settings >
# API Keys > Add API Key. It generates a config block with exactly these
# values and downloads the private key.
#
# Pass them with a terraform.tfvars file (git-ignored) or TF_VAR_ environment
# variables. Never commit them.

variable "tenancy_ocid" {
  description = "OCID of your tenancy (root compartment)."
  type        = string
}

variable "user_ocid" {
  description = "OCID of the user the API key belongs to."
  type        = string
}

variable "fingerprint" {
  description = "Fingerprint of the API signing key."
  type        = string
}

variable "private_key_path" {
  description = "Path to the API signing private key (.pem) downloaded from the console."
  type        = string
}

variable "region" {
  description = <<-EOT
    Home region of your tenancy, e.g. "us-ashburn-1".

    Worth knowing before you apply: the Always Free ARM shape is genuinely
    scarce, and popular regions return "Out of host capacity" for days at a
    time. If apply fails with that error, nothing is wrong with this config --
    retry, or create a tenancy in a quieter region.
  EOT
  type        = string
}

variable "compartment_ocid" {
  description = "Compartment to create resources in. The tenancy OCID works fine for a personal account."
  type        = string
  default     = ""
}

variable "ssh_public_key" {
  description = "Contents of your SSH public key, e.g. file(\"~/.ssh/id_ed25519.pub\")."
  type        = string
}

variable "repo_url" {
  description = "Repository cloned onto the instance at boot."
  type        = string
  default     = "https://github.com/islamborghini/clowdy.git"
}

variable "repo_branch" {
  type    = string
  default = "version_control"
}

variable "instance_ocpus" {
  description = <<-EOT
    ARM cores. The Always Free allowance is 4 OCPUs and 24GB of memory across
    all A1 instances in the tenancy, so taking all 4 here means this is your
    only ARM instance. That is the right call for this workload: function
    containers are the thing that needs headroom.
  EOT
  type        = number
  default     = 4
}

variable "instance_memory_gb" {
  type    = number
  default = 24
}

variable "allowed_ssh_cidr" {
  description = "Who may SSH in. Narrow this to your own address."
  type        = string
  default     = "0.0.0.0/0"
}
