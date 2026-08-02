[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,

    [Parameter(Mandatory = $true)]
    [string]$RequestFile,

    [string]$PolicyBundle = "",

    [string]$PythonExecutable = "python",

    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"

function Add-RepeatedArgument {
    param(
        [System.Collections.Generic.List[string]]$Arguments,
        [string]$Flag,
        [object[]]$Values
    )

    foreach ($value in @($Values)) {
        $textValue = [string]$value
        if (-not [string]::IsNullOrWhiteSpace($textValue)) {
            $Arguments.Add($Flag)
            $Arguments.Add($textValue.Trim())
        }
    }
}

$resolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
$resolvedRequestFile = (Resolve-Path -LiteralPath $RequestFile).Path
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
$cliFile = Join-Path $repoRoot "agent_writer_cli.py"

if (-not (Test-Path -LiteralPath $cliFile -PathType Leaf)) {
    throw "agent_writer_cli.py not found: $cliFile"
}

$unitRequest = Get-Content -LiteralPath $resolvedRequestFile -Raw -Encoding UTF8 | ConvertFrom-Json
if ($unitRequest.schema_version -ne "unit-request/v1") {
    throw "schema_version must be unit-request/v1."
}

$startChapter = [int]$unitRequest.start_chapter
$targetTotalChars = [int]$unitRequest.target_total_chars
if ($startChapter -lt 1) {
    throw "start_chapter must be at least 1."
}
if ($targetTotalChars -lt 1 -or $targetTotalChars -gt 20000) {
    throw "target_total_chars must be between 1 and 20000."
}

$objective = [string]$unitRequest.objective
$authorIntent = [string]$unitRequest.author_intent
if ([string]::IsNullOrWhiteSpace($objective) -or [string]::IsNullOrWhiteSpace($authorIntent)) {
    throw "objective and author_intent are required."
}

$allowedAxes = @(
    "conflict_space",
    "trigger",
    "core_mechanism",
    "climax_action",
    "cost_type",
    "end_hook"
)
$freedomAxes = @($unitRequest.freedom_axes) |
    ForEach-Object { [string]$_ } |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Select-Object -Unique
foreach ($axis in $freedomAxes) {
    if ($axis -notin $allowedAxes) {
        throw "Unknown freedom_axis: $axis"
    }
}

$planningMode = [string]$unitRequest.planning_mode
if ([string]::IsNullOrWhiteSpace($planningMode)) {
    $planningMode = "auto"
}
if ($planningMode -notin @("auto", "direct", "branch")) {
    throw "planning_mode must be auto, direct, or branch."
}

$coreMechanismLocked = [bool]$unitRequest.core_mechanism_locked
if ($planningMode -eq "auto") {
    if ((-not $coreMechanismLocked) -and $freedomAxes.Count -ge 3) {
        $planningMode = "branch"
    }
    else {
        $planningMode = "direct"
    }
}
if ($planningMode -eq "branch" -and $freedomAxes.Count -lt 3) {
    throw "Branch-first needs at least three genuinely open freedom_axes; otherwise use direct."
}

$cliArguments = [System.Collections.Generic.List[string]]::new()
$cliArguments.Add("-X")
$cliArguments.Add("utf8")
$cliArguments.Add($cliFile)
$cliArguments.Add("--project-root")
$cliArguments.Add($resolvedProjectRoot)
$cliArguments.Add($(if ($planningMode -eq "branch") { "unit-branches" } else { "unit-plan" }))
$cliArguments.Add("--start-chapter")
$cliArguments.Add([string]$startChapter)
$cliArguments.Add("--target-total-chars")
$cliArguments.Add([string]$targetTotalChars)
$cliArguments.Add("--objective")
$cliArguments.Add($objective.Trim())
$cliArguments.Add("--author-intent")
$cliArguments.Add($authorIntent.Trim())

if (-not [string]::IsNullOrWhiteSpace([string]$unitRequest.unit_title) -and $planningMode -eq "direct") {
    $cliArguments.Add("--unit-title")
    $cliArguments.Add(([string]$unitRequest.unit_title).Trim())
}
foreach ($property in @(
    @{ Name = "entry_state"; Flag = "--entry-state" },
    @{ Name = "target_end_state"; Flag = "--target-end-state" }
)) {
    $propertyValue = [string]$unitRequest.($property.Name)
    if (-not [string]::IsNullOrWhiteSpace($propertyValue)) {
        $cliArguments.Add($property.Flag)
        $cliArguments.Add($propertyValue.Trim())
    }
}

Add-RepeatedArgument -Arguments $cliArguments -Flag "--unit-payoff" -Values @($unitRequest.unit_payoffs)
Add-RepeatedArgument -Arguments $cliArguments -Flag "--lock" -Values @($unitRequest.author_locks)
Add-RepeatedArgument -Arguments $cliArguments -Flag "--forbid-change" -Values @($unitRequest.forbidden_changes)
Add-RepeatedArgument -Arguments $cliArguments -Flag "--success" -Values @($unitRequest.success_criteria)
if ($planningMode -eq "branch") {
    Add-RepeatedArgument -Arguments $cliArguments -Flag "--freedom-axis" -Values $freedomAxes
}

Write-Host "Request valid. Planning mode: $planningMode; target text limit: $targetTotalChars characters."
Write-Host "This entry point plans only. It does not write prose or select a branch for the author."

if ($ValidateOnly) {
    Write-Host "ValidateOnly is enabled; no API was called."
    exit 0
}

if (-not [string]::IsNullOrWhiteSpace($PolicyBundle)) {
    $resolvedPolicyBundle = (Resolve-Path -LiteralPath $PolicyBundle).Path
    & $PythonExecutable -X utf8 $cliFile --project-root $resolvedProjectRoot policy-import --file $resolvedPolicyBundle
    if ($LASTEXITCODE -ne 0) {
        throw "AuthorPolicy import failed with exit code $LASTEXITCODE."
    }
}

& $PythonExecutable @cliArguments
if ($LASTEXITCODE -ne 0) {
    throw "Unit planning failed with exit code $LASTEXITCODE."
}

if ($planningMode -eq "branch") {
    Write-Host "Branches created. Read unit_branches/latest_branch_set.json and require a passing diversity audit before unit-branch-select."
}
else {
    Write-Host "Unit contract created. Run unit-review, then unit-advance only after it passes."
}
