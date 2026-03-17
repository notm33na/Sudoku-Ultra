{{/*
Common labels
*/}}
{{- define "sudoku-ultra.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Selector labels for a component
Usage: include "sudoku-ultra.selectorLabels" (dict "component" "multiplayer" "root" .)
*/}}
{{- define "sudoku-ultra.selectorLabels" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/component: {{ .component }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{/*
Image string
Usage: include "sudoku-ultra.image" (dict "name" "multiplayer" "root" .)
*/}}
{{- define "sudoku-ultra.image" -}}
{{ .root.Values.image.registry }}/{{ .name }}:{{ .root.Values.image.tag }}
{{- end }}

{{/*
Global env vars injected into every service pod
*/}}
{{- define "sudoku-ultra.globalEnv" -}}
- name: DATABASE_URL
  value: {{ .Values.global.postgresUrl | quote }}
- name: REDIS_URL
  value: {{ .Values.global.redisUrl | quote }}
- name: KAFKA_BROKERS
  value: {{ .Values.global.kafkaBrokers | quote }}
- name: JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-secrets
      key: jwt-secret
- name: INTERNAL_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ .Release.Name }}-secrets
      key: internal-secret
{{- end }}
