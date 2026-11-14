param(
    [string]$Revision = "HEAD",
    [string]$OutputDirectory = ".runtime/releases"
)

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$commit = (git -C $repo rev-parse "$Revision^{commit}").Trim()
if ($LASTEXITCODE -ne 0 -or $commit -notmatch '^[0-9a-f]{40}$') {
    throw "Revision must resolve to an exact commit"
}

$tracked = @(git -C $repo ls-tree -r --name-only $commit)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to enumerate the committed tree"
}
$runtimeFiles = @($tracked | Where-Object {
    ($_ -eq "backend/__init__.py") -or
    ($_ -like "backend/app/*") -or
    ($_ -in @(
        "tools/__init__.py",
        "tools/backup.py",
        "tools/backup_rotate.py",
        "tools/manage_users.py",
        "deploy/requirements-runtime.txt",
        "deploy/systemd-production.env.example",
        "deploy/SYSTEMD_RELEASE.md",
        "deploy/systemd-user/vexplorer.service",
        "deploy/systemd-user/vexplorer-backup.service",
        "deploy/systemd-user/vexplorer-backup.timer"
    )) -or
    (
        ($_ -like "frontend/*") -and
        ($_ -notlike "frontend/tests/*") -and
        ($_ -notlike "frontend/node_modules/*") -and
        ($_ -notlike "frontend/scripts/*") -and
        ($_ -notin @(
            "frontend/.gitignore",
            "frontend/package.json",
            "frontend/package-lock.json",
            "frontend/IMPLEMENTATION_PLAN.md",
            "frontend/UX_SPEC.md"
        ))
    )
}) | Sort-Object -Unique
if ($runtimeFiles.Count -eq 0) {
    throw "The committed runtime selection is empty"
}
foreach ($required in @(
    "backend/app/main.py",
    "frontend/index.html",
    "frontend/app.js",
    "frontend/explorer.html",
    "frontend/explorer.js",
    "frontend/explorer.css",
    "frontend/vendor/three/LICENSE",
    "tools/backup.py",
    "tools/backup_rotate.py"
)) {
    if ($required -notin $runtimeFiles) {
        throw "Required runtime file is absent from the commit: $required"
    }
}

$output = if ([IO.Path]::IsPathFullyQualified($OutputDirectory)) {
    [IO.Path]::GetFullPath($OutputDirectory)
} else {
    [IO.Path]::GetFullPath((Join-Path $repo $OutputDirectory))
}
New-Item -ItemType Directory -Path $output -Force | Out-Null
$short = $commit.Substring(0, 12)
$archive = Join-Path $output "vexplorer-$commit.tar.gz"
$metadataPath = Join-Path $output "vexplorer-$commit.release.json"
if ((Test-Path -LiteralPath $archive) -or (Test-Path -LiteralPath $metadataPath)) {
    throw "Release outputs already exist for this revision"
}

$stage = Join-Path $output (".stage-" + [guid]::NewGuid().ToString("N"))
$payloadTar = Join-Path $output (".payload-" + [guid]::NewGuid().ToString("N") + ".tar")
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    git -C $repo archive --format=tar --output=$payloadTar $commit -- @runtimeFiles
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to archive the exact committed runtime"
    }
    tar -xf $payloadTar -C $stage
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to extract runtime staging payload"
    }

    $payload = @(Get-ChildItem -LiteralPath $stage -File -Recurse | Sort-Object FullName)
    $manifestLines = foreach ($item in $payload) {
        $relative = $item.FullName.Substring($stage.Length + 1).Replace("\", "/")
        $digest = (Get-FileHash -Algorithm SHA256 -LiteralPath $item.FullName).Hash.ToLowerInvariant()
        "$digest  $($item.Length)  $relative"
    }
    (($manifestLines -join "`n") + "`n") | Set-Content -LiteralPath (Join-Path $stage "MANIFEST.sha256") -Encoding utf8NoBOM -NoNewline
    $release = [ordered]@{
        format = "vexplorer-runtime-release-v2"
        git_head = $commit
        created_at_utc = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
        runtime_files = $payload.Count
    }
    (($release | ConvertTo-Json) + "`n") | Set-Content -LiteralPath (Join-Path $stage "RELEASE.json") -Encoding utf8NoBOM -NoNewline

    tar -C $stage -czf $archive .
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create release archive"
    }
    $entries = @(tar -tzf $archive)
    $forbidden = @($entries | Where-Object {
        $_ -match '(^|/)(tests?|evaluation|node_modules|__pycache__)(/|$)|\.pyc$|(^|/)\.env$'
    })
    if ($forbidden.Count -ne 0) {
        throw "Forbidden release entries: $($forbidden -join ', ')"
    }
    $metadata = [ordered]@{
        revision = $commit
        archive = (Split-Path -Leaf $archive)
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
        size_bytes = (Get-Item -LiteralPath $archive).Length
        entries = $entries.Count
    }
    (($metadata | ConvertTo-Json) + "`n") | Set-Content -LiteralPath $metadataPath -Encoding utf8NoBOM -NoNewline
    $metadata | ConvertTo-Json
}
finally {
    Remove-Item -LiteralPath $payloadTar -Force -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $stage) {
        $resolvedStage = (Resolve-Path -LiteralPath $stage).Path
        if (-not $resolvedStage.StartsWith($output + [IO.Path]::DirectorySeparatorChar)) {
            throw "Unsafe staging path"
        }
        Remove-Item -LiteralPath $resolvedStage -Recurse -Force
    }
}
