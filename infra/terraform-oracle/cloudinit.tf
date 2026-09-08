# First-boot provisioning.
#
# Two things here are specific to Oracle's Ubuntu images and are the usual
# reason a first deploy appears to succeed and then times out in the browser:
#
#   1. The image ships an iptables INPUT policy that drops everything except
#      SSH. Opening port 80 in the VCN security list is necessary but not
#      sufficient -- the host firewall has to allow it too.
#   2. That ruleset is persisted by netfilter-persistent, so the rule has to
#      be saved or it disappears on the next reboot.

locals {
  cloud_init = <<-CLOUDINIT
    #!/bin/bash
    set -euxo pipefail

    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y ca-certificates curl git iptables-persistent

    # Docker, from Docker's own repository: Ubuntu's packaged version does not
    # ship the compose v2 plugin this stack uses.
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
      -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=arm64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    usermod -aG docker ubuntu

    # Let the world reach the frontend. Insert above the image's catch-all
    # REJECT rule rather than appending after it.
    iptables -I INPUT 1 -p tcp --dport 80 -j ACCEPT
    iptables -I INPUT 2 -p tcp --dport 443 -j ACCEPT
    netfilter-persistent save

    git clone --branch ${var.repo_branch} ${var.repo_url} /opt/clowdy
    chown -R ubuntu:ubuntu /opt/clowdy

    # No API keys on the demo box. Without them the AI assistant and managed
    # databases are inert, which suits a read-only deployment, and there are
    # no secrets on a public host to leak.
    touch /opt/clowdy/.env
    chown ubuntu:ubuntu /opt/clowdy/.env

    cd /opt/clowdy
    docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build

    # Give the control plane a moment to finish starting, then seed the
    # example functions. The seeder is idempotent, so a retry is harmless.
    for attempt in $(seq 1 30); do
      if docker compose -f docker-compose.yml -f docker-compose.demo.yml            exec -T control-plane python -m app.seed_demo; then
        break
      fi
      sleep 5
    done

    # Bring the stack back after a reboot.
    cat > /etc/systemd/system/clowdy.service <<'UNIT'
    [Unit]
    Description=Clowdy
    Requires=docker.service
    After=docker.service

    [Service]
    Type=oneshot
    RemainAfterExit=yes
    WorkingDirectory=/opt/clowdy
    ExecStart=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d
    ExecStop=/usr/bin/docker compose -f docker-compose.yml -f docker-compose.demo.yml down

    [Install]
    WantedBy=multi-user.target
    UNIT
    systemctl enable clowdy.service

    echo "clowdy: first boot complete"
  CLOUDINIT
}
