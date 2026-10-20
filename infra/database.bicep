// Gridcast on Azure, step 1: the PostgreSQL database with pgvector.
//
// Deploy:
//   az deployment group create --resource-group gridcast-rg \
//     --template-file infra/database.bicep \
//     --parameters adminPassword="$PGPASSWORD" clientIp="$(curl -s https://api.ipify.org)"

@description('Region for the database. West Europe did not accept new database customers, so North Europe is the default.')
param location string = 'northeurope'

@description('Administrator user name.')
param adminUser string = 'gridcast'

@secure()
@description('Administrator password. Pass it at deployment time; never commit it.')
param adminPassword string

@description('Your public IP address. Only this address and Azure services can reach the database.')
param clientIp string

var serverName = 'gridcast-pg-${uniqueString(resourceGroup().id)}'

resource server 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: serverName
  location: location
  sku: {
    name: 'Standard_B1ms' // smallest burstable size; part of the free-account offer
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: adminUser
    administratorLoginPassword: adminPassword
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
  }
}

// pgvector must be allow-listed before "create extension vector" can run.
resource extensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: server
  name: 'azure.extensions'
  properties: {
    value: 'VECTOR'
    source: 'user-override'
  }
}

// The server accepts one change at a time, so the children run in sequence.
resource database 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: server
  name: 'gridcast'
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
  dependsOn: [
    extensions
  ]
}

resource clientRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'client-ip'
  properties: {
    startIpAddress: clientIp
    endIpAddress: clientIp
  }
  dependsOn: [
    database
  ]
}

// 0.0.0.0 is Azure's convention for "allow Azure services", such as Container Apps.
resource azureRule 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: server
  name: 'allow-azure-services'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
  dependsOn: [
    clientRule
  ]
}

output host string = server.properties.fullyQualifiedDomainName
output databaseName string = database.name
output adminUser string = adminUser
