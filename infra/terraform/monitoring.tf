# ──────────────────────────────────────────────────────────────────────────────
# monitoring.tf — Grafana Cloud + Alertmanager Terraform resources
#
# Manages:
#   - Grafana Cloud stack (Prometheus remote-write, Loki, Tempo endpoints)
#   - Grafana service accounts and API keys for CI (read-only + dashboard-push)
#   - Dashboard folders and dashboard provisioning via grafana_dashboard resource
#   - Alerting contact points (Slack) and notification policies
#   - Alertmanager configuration in Grafana Cloud
#
# Provider docs:
#   registry.terraform.io/providers/grafana/grafana
# ──────────────────────────────────────────────────────────────────────────────

terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 3.0"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "grafana_cloud_url" {
  description = "Grafana Cloud stack URL, e.g. https://sudoku-ultra.grafana.net"
  type        = string
}

variable "grafana_cloud_api_key" {
  description = "Grafana Cloud API key with Admin role (from grafana.com → API keys)"
  type        = string
  sensitive   = true
}

variable "grafana_cloud_org_slug" {
  description = "Grafana Cloud organisation slug"
  type        = string
  default     = "sudoku-ultra"
}

variable "slack_webhook_url" {
  description = "Slack incoming webhook URL for alert notifications"
  type        = string
  sensitive   = true
  default     = ""
}

variable "slack_alert_channel" {
  description = "Slack channel for critical alerts"
  type        = string
  default     = "#devops-alerts"
}

variable "slack_deploy_channel" {
  description = "Slack channel for deploy / info notifications"
  type        = string
  default     = "#deploys"
}

# ── Provider ───────────────────────────────────────────────────────────────────

provider "grafana" {
  url  = var.grafana_cloud_url
  auth = var.grafana_cloud_api_key
}

# ── Service accounts ───────────────────────────────────────────────────────────

resource "grafana_service_account" "ci_push" {
  name        = "ci-dashboard-push"
  role        = "Editor"
  is_disabled = false
}

resource "grafana_service_account_token" "ci_push" {
  name               = "ci-push-token"
  service_account_id = grafana_service_account.ci_push.id
  # Rotate every 365 days — update in CI secrets after rotation
  seconds_to_live = 365 * 24 * 3600
}

resource "grafana_service_account" "read_only" {
  name        = "monitoring-readonly"
  role        = "Viewer"
  is_disabled = false
}

resource "grafana_service_account_token" "read_only" {
  name               = "readonly-token"
  service_account_id = grafana_service_account.read_only.id
  seconds_to_live    = 365 * 24 * 3600
}

# ── Dashboard folders ──────────────────────────────────────────────────────────

resource "grafana_folder" "app" {
  title = "Application"
  uid   = "app"
}

resource "grafana_folder" "ml" {
  title = "Machine Learning"
  uid   = "ml"
}

resource "grafana_folder" "infra" {
  title = "Infrastructure"
  uid   = "infra"
}

resource "grafana_folder" "business" {
  title = "Business"
  uid   = "business"
}

# ── Dashboards ─────────────────────────────────────────────────────────────────

locals {
  dashboards = {
    app        = { folder = grafana_folder.app.uid,      path = "${path.module}/../grafana/dashboards/app.json" }
    ml         = { folder = grafana_folder.ml.uid,       path = "${path.module}/../grafana/dashboards/ml.json" }
    multiplayer = { folder = grafana_folder.app.uid,     path = "${path.module}/../grafana/dashboards/multiplayer.json" }
    infra      = { folder = grafana_folder.infra.uid,    path = "${path.module}/../grafana/dashboards/infra.json" }
    business   = { folder = grafana_folder.business.uid, path = "${path.module}/../grafana/dashboards/business.json" }
  }
}

resource "grafana_dashboard" "dashboards" {
  for_each    = local.dashboards
  folder      = each.value.folder
  config_json = file(each.value.path)
  overwrite   = true
}

# ── Data sources (Grafana Cloud managed endpoints) ─────────────────────────────

resource "grafana_data_source" "prometheus" {
  name       = "Prometheus"
  type       = "prometheus"
  url        = "${var.grafana_cloud_url}/api/prom"
  is_default = true

  json_data_encoded = jsonencode({
    httpMethod          = "POST"
    prometheusType      = "Prometheus"
    prometheusVersion   = "2.53.0"
    incrementalQuerying = true
  })
}

resource "grafana_data_source" "loki" {
  name = "Loki"
  type = "loki"
  url  = "${var.grafana_cloud_url}/loki"

  json_data_encoded = jsonencode({
    derivedFields = [
      {
        name            = "TraceID"
        matcherRegex    = "\"trace_id\":\"(\\w+)\""
        url             = "${var.grafana_cloud_url}/explore?orgId=1&left=%5B%22now-1h%22,%22now%22,%22Tempo%22,%7B%22query%22:%22$${__value.raw}%22%7D%5D"
        datasourceUid   = grafana_data_source.tempo.uid
      }
    ]
  })
}

resource "grafana_data_source" "tempo" {
  name = "Tempo"
  type = "tempo"
  url  = "${var.grafana_cloud_url}/tempo"

  json_data_encoded = jsonencode({
    tracesToLogsV2 = {
      datasourceUid = grafana_data_source.loki.uid
      spanStartTimeShift = "-1m"
      spanEndTimeShift   = "1m"
    }
    serviceMap = { datasourceUid = grafana_data_source.prometheus.uid }
    search     = { hide = false }
    nodeGraph  = { enabled = true }
  })
}

# ── Alerting contact points ────────────────────────────────────────────────────

resource "grafana_contact_point" "slack_alerts" {
  count = var.slack_webhook_url != "" ? 1 : 0
  name  = "slack-alerts"

  slack {
    url       = var.slack_webhook_url
    recipient = var.slack_alert_channel
    title     = "[{{ .CommonLabels.alertname }}] {{ .CommonAnnotations.summary }}"
    text      = "{{ range .Alerts }}{{ .Annotations.description }}{{ end }}"
    mention_channel = "here"
  }
}

resource "grafana_contact_point" "slack_deploys" {
  count = var.slack_webhook_url != "" ? 1 : 0
  name  = "slack-deploys"

  slack {
    url       = var.slack_webhook_url
    recipient = var.slack_deploy_channel
    title     = "{{ .CommonLabels.alertname }}"
    text      = "{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}"
  }
}

# ── Notification policy ────────────────────────────────────────────────────────

resource "grafana_notification_policy" "main" {
  count              = var.slack_webhook_url != "" ? 1 : 0
  contact_point      = grafana_contact_point.slack_alerts[0].name
  group_by           = ["alertname", "service"]
  group_wait         = "30s"
  group_interval     = "5m"
  repeat_interval    = "4h"

  policy {
    matcher {
      label = "severity"
      match = "="
      value = "critical"
    }
    contact_point  = grafana_contact_point.slack_alerts[0].name
    group_by       = ["alertname"]
    group_wait     = "10s"
    group_interval = "1m"
    repeat_interval = "1h"
  }

  policy {
    matcher {
      label = "severity"
      match = "="
      value = "warning"
    }
    contact_point   = grafana_contact_point.slack_deploys[0].name
    group_by        = ["alertname"]
    repeat_interval = "12h"
  }
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "grafana_ci_push_token" {
  description = "Grafana service account token for CI dashboard uploads (store in GitHub Actions secret GRAFANA_CI_TOKEN)"
  value       = grafana_service_account_token.ci_push.key
  sensitive   = true
}

output "grafana_readonly_token" {
  description = "Read-only Grafana token for external tooling"
  value       = grafana_service_account_token.read_only.key
  sensitive   = true
}
