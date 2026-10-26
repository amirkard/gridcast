{{/* Release-based name, at most 63 characters. */}}
{{- define "gridcast.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "gridcast.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "gridcast.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "gridcast.image" -}}
{{- printf "%s:%s" .Values.image.repository (toString .Values.image.tag) -}}
{{- end -}}

{{- define "gridcast.secretName" -}}
{{- .Values.secrets.existingSecret | default (include "gridcast.fullname" .) -}}
{{- end -}}

{{- define "gridcast.postgresName" -}}
{{- printf "%s-postgres" (include "gridcast.fullname" .) -}}
{{- end -}}

{{/* The API, the migration step, and the ingest job all need the database. */}}
{{- define "gridcast.databaseEnv" -}}
{{- if .Values.postgres.enabled }}
- name: PGPASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "gridcast.postgresName" . }}
      key: password
- name: DATABASE_URL
  value: {{ printf "postgresql+psycopg://%s:$(PGPASSWORD)@%s:5432/%s" .Values.postgres.user (include "gridcast.postgresName" .) .Values.postgres.database | quote }}
{{- else }}
{{- if not (or .Values.secrets.existingSecret (and .Values.secrets.create .Values.secrets.databaseUrl)) }}
{{- fail "No database: set postgres.enabled=true, or secrets.existingSecret with a DATABASE_URL key, or secrets.create=true with secrets.databaseUrl." }}
{{- end }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ include "gridcast.secretName" . }}
      key: DATABASE_URL
{{- end }}
{{- end -}}

{{/* Unprivileged user from the Dockerfile. */}}
{{- define "gridcast.podSecurityContext" -}}
runAsNonRoot: true
runAsUser: 10001
runAsGroup: 10001
seccompProfile:
  type: RuntimeDefault
{{- end -}}

{{- define "gridcast.containerSecurityContext" -}}
allowPrivilegeEscalation: false
capabilities:
  drop: ["ALL"]
{{- end -}}
