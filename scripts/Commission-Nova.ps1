[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Observation,
    [Parameter(Mandatory)][string]$Output,
    [string]$Config = (Join-Path $PSScriptRoot '../configs/lagoon-astrometry.example.yaml'),
    [switch]$AuthorizeUpload
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
if (!$env:OSP_ASTROMETRY_API_KEY) {
    $secret = Read-Host 'Enter a rotated Nova API key for this process' -AsSecureString
    $env:OSP_ASTROMETRY_API_KEY = [Net.NetworkCredential]::new('', $secret).Password
    Remove-Variable secret
    $loadedHere = $true
}
try {
    osp astrometry probe --backend online --config $Config
    if ($LASTEXITCODE -ne 0) { throw 'Nova probe failed. No observation was submitted.' }
    if (!$AuthorizeUpload) { return }
    $raw = (Resolve-Path -LiteralPath $Observation).Path
    $before = (Get-FileHash -LiteralPath $raw -Algorithm SHA256).Hash
    try {
        osp astrometry solve $raw --backend online --allow-online --config $Config --output $Output
        if ($LASTEXITCODE -ne 0) { throw 'Read the validation report or use astrometry status with the saved receipt.' }
    } finally {
        if ((Get-FileHash -LiteralPath $raw -Algorithm SHA256).Hash -ne $before) {
            throw 'Raw FITS checksum changed during the run.'
        }
    }
} finally {
    if ($loadedHere) { Remove-Item Env:OSP_ASTROMETRY_API_KEY -ErrorAction SilentlyContinue }
}
