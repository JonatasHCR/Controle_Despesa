<#
.SYNOPSIS
    Restaura um backup .sql no banco do Controle de Despesa.
.DESCRIPTION
    Para .dump (formato custom), use o painel administrativo ou pg_restore.
    Este script cobre os .sql gerados pelo sidecar e pelo backup-db.sh.
#>
param([Parameter(Mandatory)] [string]$Arquivo)

$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')

$caminho = if (Test-Path $Arquivo) { $Arquivo } else { Join-Path 'backups' $Arquivo }
if (-not (Test-Path $caminho)) { throw "nao achei $caminho" }

# Sem os DROPs, restaurar por cima de um banco povoado aplica so os COPY que
# nao conflitam e deixa o banco num estado misturado.
if (-not (Select-String -Path $caminho -Pattern '^DROP ' -Quiet)) {
    throw "$caminho nao tem comandos DROP; gere o dump com --clean --if-exists"
}

Write-Host "Isto SUBSTITUI o conteudo do banco pelo de $caminho." -ForegroundColor Yellow
if ((Read-Host 'Digite RESTAURAR para confirmar') -cne 'RESTAURAR') {
    Write-Host 'Cancelado.' -ForegroundColor Yellow
    return
}

Get-Content -Raw $caminho | docker compose exec -T db psql `
    --set ON_ERROR_STOP=1 --single-transaction `
    -U $env:POSTGRES_USER -d $env:POSTGRES_DB

Write-Host 'Restaurado.' -ForegroundColor Green
