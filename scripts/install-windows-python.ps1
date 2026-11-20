param([Parameter(Mandatory)][string]$Destination)

$ErrorActionPreference = 'Stop'
$release = 'https://github.com/astral-sh/python-build-standalone/releases/download/20261110/cpython-3.12.16%2B20261110-x86_64-pc-windows-msvc-install_only.tar.gz'
$expected = 'e23fe5b16926de1d81661b1a97352e89fb167549c55a6825796ccd0f32ec7f1b'
$root = New-Item -ItemType Directory -Path $Destination -Force
$archive = Join-Path $root.FullName 'python-3.12.16-windows-x64.tar.gz'

Invoke-WebRequest -Uri $release -OutFile $archive
if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash -ne $expected) {
    throw 'Windows Python archive checksum mismatch'
}
tar.exe -xzf $archive -C $root.FullName
if ($LASTEXITCODE -ne 0) { throw 'Windows Python archive could not be extracted' }

Join-Path $root.FullName 'python/python.exe'
