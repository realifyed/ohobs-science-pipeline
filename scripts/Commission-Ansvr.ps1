[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Observation,
    [Parameter(Mandatory)][string]$Output,
    [string]$Osp = 'osp',
    [string]$AnsvrRoot = (Join-Path $env:LOCALAPPDATA 'cygwin_ansvr'),
    [ValidateRange(0,65535)][int]$Port = 0,
    [ValidateRange(5,900)][int]$TimeoutSeconds = 120,
    [string]$GaiaCatalogue,
    [string]$IndexManifest,
    [string]$IndependenceEvidence,
    [double]$MaxRmsArcsec = 0,
    [switch]$ProbeDirect
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$utf8 = New-Object System.Text.UTF8Encoding($false)
function Write-Utf8([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content + [Environment]::NewLine, $utf8)
}

$raw = (Resolve-Path -LiteralPath $Observation).Path
if (Test-Path -LiteralPath $Output) { throw 'Choose a new output directory.' }
$out = (New-Item -ItemType Directory -Path $Output).FullName
$before = (Get-FileHash -Algorithm SHA256 -LiteralPath $raw).Hash
$logRoot = Join-Path $AnsvrRoot 'var\tmp\platesolve'
$logs = @(Get-ChildItem -LiteralPath $logRoot -Filter 'ansvr_*.log' -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending)
$startup = @($logs | Select-Object -First 4 | ForEach-Object {
    Select-String -LiteralPath $_.FullName -Pattern 'ansvr .* start','astrometry.net version',
        'read port [0-9]+ from reg','accepting clients','setup server:' |
        ForEach-Object Line
})
$portFrom = 'argument'
if ($Port -eq 0) {
    try {
        $Port = [int](Get-ItemPropertyValue -Path 'HKCU:\Software\adgsoftware\ansvr' -Name 'port')
        $portFrom = 'registry'
    } catch {
        $line = $startup | Where-Object { $_ -match 'read port [0-9]+ from reg' } | Select-Object -First 1
        if ($line -match 'read port ([0-9]+) from reg') {
            $Port = [int]$Matches[1]
            $portFrom = 'ANSVR startup log'
        } else {
            $Port = 8080
            $portFrom = 'ANSVR default'
        }
    }
}

$url = "http://127.0.0.1:$Port"
$names = @('bin\bash.exe', 'bin\cygpath.exe', 'bin\cygwin1.dll',
    'lib\astrometry\bin\solve-field.exe')
$runtime = @(foreach ($name in $names) {
    $path = Join-Path $AnsvrRoot $name
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $item = Get-Item -LiteralPath $path
        [ordered]@{ name = $name; bytes = $item.Length; sha256 = (
            Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash }
    } else { [ordered]@{ name = $name; missing = $true } }
})
$indexes = @(Get-ChildItem -LiteralPath (Join-Path $AnsvrRoot 'usr\share\astrometry\data') `
    -File -Filter 'index-*.fits' -ErrorAction SilentlyContinue | Sort-Object Name |
    Select-Object Name, Length)
$listener = @()
try {
    $listener = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop |
        Select-Object LocalAddress, LocalPort, OwningProcess)
} catch { $listener = @($_.Exception.Message) }
$diagnostics = [ordered]@{
    url = $url; port_source = $portFrom; powershell = $PSVersionTable.PSVersion.ToString()
    os = [Environment]::OSVersion.VersionString; process_64bit = [Environment]::Is64BitProcess
    ansvr_root = $AnsvrRoot; local_app_data = $env:LOCALAPPDATA; listener = $listener
    startup = $startup; runtime = $runtime; indexes = $indexes; raw_sha256_before = $before
}

try {
    Get-Command $Osp -ErrorAction Stop | Out-Null
    $gaia = $null
    $manifest = $null
    if ($GaiaCatalogue) { $gaia = (Resolve-Path -LiteralPath $GaiaCatalogue).Path }
    if ($IndexManifest) { $manifest = (Resolve-Path -LiteralPath $IndexManifest).Path }
    if ($IndependenceEvidence -or $MaxRmsArcsec -gt 0) {
        if (!$gaia -or !$manifest -or !$IndependenceEvidence -or $MaxRmsArcsec -le 0) {
            throw 'To request verification supply GaiaCatalogue, IndexManifest, IndependenceEvidence and MaxRmsArcsec.'
        }
    }
    $astrometry = [ordered]@{
        backend = 'ansvr_http'; ansvr_url = $url; timeout_s = $TimeoutSeconds
        scale_min = 0.95; scale_max = 1.19; pointing_radius_deg = 2
        catalogue = $gaia; index_manifest = $manifest
    }
    if ($IndependenceEvidence) {
        $astrometry['catalogue_independence_evidence'] = $IndependenceEvidence
        $astrometry['max_rms_arcsec'] = $MaxRmsArcsec
    }
    $config = Join-Path $out 'ansvr.yaml'
    $configData = @{
        node = 'OHOBS-01'; astrometry = $astrometry
        quality = @{ detection_smoothing_sigma_px = 3; fit_radius = 12; max_sources = 220 }
    }
    # JSON is a supported input subset of the OSP YAML parser.
    Write-Utf8 $config ($configData | ConvertTo-Json -Depth 6)
    $probe = & $Osp astrometry probe --config $config 2> (Join-Path $out 'probe-error.log')
    $probeExit = $LASTEXITCODE
    Write-Utf8 (Join-Path $out 'probe.json') ($probe -join [Environment]::NewLine)
    if ($ProbeDirect) {
        $directConfig = Join-Path $out 'direct.yaml'
        $configData.astrometry = @{ backend = 'ansvr'; ansvr_root = $AnsvrRoot; timeout_s = 10 }
        Write-Utf8 $directConfig ($configData | ConvertTo-Json -Depth 6)
        $direct = & $Osp astrometry probe --config $directConfig 2> (Join-Path $out 'direct-error.log')
        Write-Utf8 (Join-Path $out 'direct.json') ($direct -join [Environment]::NewLine)
    }
    if ($probeExit -ne 0) {
        throw 'ANSVR API probe failed. Open Ansvr Settings and inspect Watch Ansvr Log, then retry with a new output directory.'
    }
    $solution = & $Osp astrometry diagnose-raw $raw --config $config `
        --output (Join-Path $out 'solve') 2> (Join-Path $out 'solve-error.log')
    $solveExit = $LASTEXITCODE
    Write-Utf8 (Join-Path $out 'solve.json') ($solution -join [Environment]::NewLine)
    if ($solveExit -ne 0) { throw 'ANSVR raw solve failed. See solve-error.log and solve\validation.json.' }
    if ($IndependenceEvidence -and (($solution -join "`n") | ConvertFrom-Json).status -ne 'VERIFIED') {
        throw 'The candidate WCS did not pass Gaia verification. See solve\validation.json.'
    }
    Write-Output $solution
} finally {
    $diagnostics['raw_sha256_after'] = (Get-FileHash -Algorithm SHA256 -LiteralPath $raw).Hash
    $diagnostics['raw_sha256_unchanged'] = $diagnostics['raw_sha256_after'] -eq $before
    Write-Utf8 (Join-Path $out 'windows-diagnostics.json') ($diagnostics | ConvertTo-Json -Depth 7)
}
