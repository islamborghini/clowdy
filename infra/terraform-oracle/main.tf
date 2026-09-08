# Clowdy on Oracle Cloud's Always Free tier.
#
# 4 ARM cores and 24GB of memory, free permanently -- no 12-month cliff and no
# spend to forget about. That is a genuinely generous box for this workload:
# the platform itself idles around 430MB, so nearly everything is headroom for
# function containers.
#
# It deploys the read-only demo overlay. The host executes Python from anyone
# who can reach it, so DEMO_MODE blocks every write at the API edge; see
# backend/app/middleware/demo_mode.py.
#
#   terraform init
#   terraform apply
#
# The one thing that will bite you: the A1 ARM shape is heavily oversubscribed
# and popular regions return "Out of host capacity". That is a capacity error,
# not a config error. Retry, or pick a quieter region.

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

# Latest Canonical Ubuntu 24.04 for aarch64. Looked up rather than hardcoded
# because image OCIDs differ per region and are replaced on every release.
data "oci_core_images" "ubuntu_arm" {
  compartment_id           = local.compartment
  operating_system         = "Canonical Ubuntu"
  operating_system_version = "24.04"
  shape                    = "VM.Standard.A1.Flex"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# --- Network ---------------------------------------------------------------

resource "oci_core_vcn" "main" {
  compartment_id = local.compartment
  display_name   = local.name
  cidr_blocks    = ["10.0.0.0/16"]
  dns_label      = "clowdy"
}

resource "oci_core_internet_gateway" "main" {
  compartment_id = local.compartment
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.name
  enabled        = true
}

resource "oci_core_route_table" "main" {
  compartment_id = local.compartment
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.name

  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

resource "oci_core_security_list" "main" {
  compartment_id = local.compartment
  vcn_id         = oci_core_vcn.main.id
  display_name   = local.name

  egress_security_rules {
    destination = "0.0.0.0/0"
    protocol    = "all"
  }

  ingress_security_rules {
    protocol    = "6" # TCP
    source      = "0.0.0.0/0"
    description = "HTTP"
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = "0.0.0.0/0"
    description = "HTTPS, once a certificate is in place"
    tcp_options {
      min = 443
      max = 443
    }
  }

  ingress_security_rules {
    protocol    = "6"
    source      = var.allowed_ssh_cidr
    description = "SSH"
    tcp_options {
      min = 22
      max = 22
    }
  }
}

resource "oci_core_subnet" "main" {
  compartment_id    = local.compartment
  vcn_id            = oci_core_vcn.main.id
  cidr_block        = "10.0.1.0/24"
  display_name      = local.name
  route_table_id    = oci_core_route_table.main.id
  security_list_ids = [oci_core_security_list.main.id]
  dns_label         = "public"
}

# --- Instance --------------------------------------------------------------

resource "oci_core_instance" "app" {
  compartment_id      = local.compartment
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = local.name
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus         = var.instance_ocpus
    memory_in_gbs = var.instance_memory_gb
  }

  lifecycle {
    precondition {
      condition     = length(data.oci_core_images.ubuntu_arm.images) > 0
      error_message = "No Ubuntu 24.04 aarch64 image found for VM.Standard.A1.Flex in ${var.region}. That shape is not offered in every region -- check the region supports A1, or adjust operating_system_version in the image data source."
    }
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
    # Always Free includes 200GB of block volume. 100GB leaves room for a
    # second instance and is far more than the images need.
    boot_volume_size_in_gbs = 100
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.main.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data           = base64encode(local.cloud_init)
  }
}

output "url" {
  value = "http://${oci_core_instance.app.public_ip}"
}

output "ssh" {
  value = "ssh ubuntu@${oci_core_instance.app.public_ip}"
}

output "first_boot_note" {
  value = "Cloud-init clones the repo and builds four images on an ARM box; allow 5-10 minutes before the URL responds. Watch it with: ssh ubuntu@${oci_core_instance.app.public_ip} 'sudo tail -f /var/log/cloud-init-output.log'"
}
