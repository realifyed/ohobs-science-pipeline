[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Osp,
    [Parameter(Mandatory)][string]$Output,
    [string]$Fixture = (Join-Path $PSScriptRoot '../examples/core-smoke-fixture.zip')
)
$ErrorActionPreference = 'Stop'
function Invoke-Osp {
    $result = & $Osp @args
    if ($LASTEXITCODE) { throw "OSP command failed with exit $LASTEXITCODE" }
    return $result
}
Invoke-Osp doctor | Out-Null
if (Test-Path -LiteralPath $Output) { throw 'Output already exists' }
Expand-Archive -LiteralPath $Fixture -DestinationPath $Output
$cfg = Join-Path $Output 'simulation.yaml'
$d = @(Get-ChildItem (Join-Path $Output 'dark/*.fits') | ForEach-Object FullName)
$fd = @(Get-ChildItem (Join-Path $Output 'flat_dark/*.fits') | ForEach-Object FullName)
$f = @(Get-ChildItem (Join-Path $Output 'flat/*.fits') | ForEach-Object FullName)
Invoke-Osp masters build --config $cfg --kind DARK @d | Out-Null
$short = Invoke-Osp masters build --config $cfg --kind FLAT_DARK @fd | ConvertFrom-Json
Invoke-Osp masters build --config $cfg --kind FLAT --flat-dark $short.id @f | Out-Null
$light = Join-Path $Output 'light/light-00000.fits'
$product = Invoke-Osp reduce $light --config $cfg | ConvertFrom-Json
Invoke-Osp validate $product.path
Invoke-Osp report --product $product.path --html (Join-Path $Output 'exposure.html') | Out-Null
$batch = Invoke-Osp batch (Join-Path $Output 'light') --config $cfg | ConvertFrom-Json
Invoke-Osp report --job $batch.id --config $cfg --html (Join-Path $Output 'batch.html')
