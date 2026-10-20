// Gridcast on Azure, step 2: the API as a container, with its secrets in Key Vault.
//
// Creates a Log Analytics workspace (container logs), a Key Vault with the three
// secrets, a managed identity that may read them, a Container Apps environment,
// and the container app itself. The app scales to zero when nobody calls it.
//
// Deploy (after infra/database.bicep):
//   az deployment group create --resource-group gridcast-rg \
//     --template-file infra/app.bicep \
//     --parameters databaseUrl="$AZURE_DATABASE_URL" anthropicApiKey="$ANTHROPIC_API_KEY" askToken="$ASK_TOKEN"

@description('Region for all resources.')
param location string = 'northeurope'

@description('Container image to run. CI publishes it to the GitHub Container Registry.')
param image string = 'ghcr.io/amirkard/gridcast:latest'

@secure()
@description('SQLAlchemy URL of the Azure database, with sslmode=require.')
param databaseUrl string

@secure()
@description('Anthropic API key for the agent behind /ask.')
param anthropicApiKey string

@secure()
@description('Shared token that callers of /ask must send in the X-Ask-Token header.')
param askToken string

var suffix = uniqueString(resourceGroup().id)

// Built-in role "Key Vault Secrets User": read secret values, nothing else.
var keyVaultSecretsUser = subscriptionResourceId(
  'Microsoft.Authorization/roleDefinitions',
  '4633458b-17de-408a-b874-0445c86b69e6'
)

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'gridcast-logs-${suffix}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'gckv${suffix}'
  location: location
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
  }
}

resource dbSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'database-url'
  properties: {
    value: databaseUrl
  }
}

resource apiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'anthropic-api-key'
  properties: {
    value: anthropicApiKey
  }
}

resource askTokenSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'ask-token'
  properties: {
    value: askToken
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'gridcast-app-id'
  location: location
}

resource canReadSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: vault
  name: guid(vault.id, identity.id, keyVaultSecretsUser)
  properties: {
    roleDefinitionId: keyVaultSecretsUser
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'gridcast-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'gridcast-api'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
      }
      // The app reads its secrets from Key Vault through the managed identity;
      // no secret value is stored in the app definition.
      secrets: [
        {
          name: 'database-url'
          keyVaultUrl: dbSecret.properties.secretUri
          identity: identity.id
        }
        {
          name: 'anthropic-api-key'
          keyVaultUrl: apiKeySecret.properties.secretUri
          identity: identity.id
        }
        {
          name: 'ask-token'
          keyVaultUrl: askTokenSecret.properties.secretUri
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'ASK_TOKEN'
              secretRef: 'ask-token'
            }
          ]
          probes: [
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0 // no cost while idle; the first call after a pause waits for a cold start
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    canReadSecrets // the identity must be able to read the secrets before the app starts
  ]
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output keyVaultName string = vault.name
