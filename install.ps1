Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$composeUrl = $env:ORION_COMPOSE_URL
if ([string]::IsNullOrWhiteSpace($composeUrl)) {
  $composeUrl = "https://raw.githubusercontent.com/krstalacam/orion-router/main/docker-compose.ghcr.yml"
}

$envExampleUrl = $env:ORION_ENV_EXAMPLE_URL
if ([string]::IsNullOrWhiteSpace($envExampleUrl)) {
  $envExampleUrl = "https://raw.githubusercontent.com/krstalacam/orion-router/main/.env.example"
}

$projectName = "orion-router"
$networkName = $env:ORION_NETWORK
if ([string]::IsNullOrWhiteSpace($networkName)) {
  $networkName = "orion-network"
}

try {
  Get-Command docker -ErrorAction Stop | Out-Null
} catch {
  Write-Error "Docker not found. Please install Docker Desktop first."
  exit 1
}

try {
  docker compose version | Out-Null
} catch {
  Write-Error "Docker Compose is not available. Please update Docker Desktop."
  exit 1
}

$workDir = Join-Path $env:USERPROFILE ".orion-router"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$composeFile = Join-Path $workDir "docker-compose.ghcr.yml"
$envExampleFile = Join-Path $workDir ".env.example"
$envFile = Join-Path $workDir ".env"

Invoke-WebRequest -Uri $composeUrl -OutFile $composeFile -UseBasicParsing
Invoke-WebRequest -Uri $envExampleUrl -OutFile $envExampleFile -UseBasicParsing

$hasServices = Select-String -Path $composeFile -Pattern "^services:" -Quiet
if (-not $hasServices) {
  throw "Downloaded file does not look like a Docker Compose file."
}

if (-not (Test-Path $envFile)) {
  Copy-Item -Path $envExampleFile -Destination $envFile
}

$existingNetwork = docker network inspect $networkName 2>$null
if (-not $existingNetwork) {
  docker network create $networkName | Out-Null
} else {
  Write-Host "Network already exists: $networkName"
}

$containerNames = @("router", "router-db")
foreach ($name in $containerNames) {
  $exists = docker ps -a --format "{{.Names}}" | Where-Object { $_ -eq $name }
  if ($exists) {
    $label = $null
    try {
      $inspect = docker inspect $name 2>$null | ConvertFrom-Json
      if ($inspect -and $inspect[0].Config.Labels) {
        $label = $inspect[0].Config.Labels."com.docker.compose.project"
      }
    } catch {
    }
    if ($label -and $label -ne $projectName) {
      Write-Host "Removing conflicting container: $name (project $label)"
      docker rm -f $name | Out-Null
    } else {
      Write-Host "Container already exists: $name"
    }
  }
}

Push-Location $workDir
try {
  docker compose --project-name $projectName -f $composeFile up -d
  Write-Host "Orion Router is up. Dashboard: http://localhost:20128/dashboard"
} finally {
  Pop-Location
}