$threads = @(1,2,4,8,16,20)

$output = "experiments/raw/spend_thread_scaling.csv"

Write-Host "threads,prove_ms,verify_ms"

foreach ($t in $threads) {

    Write-Host ""
    Write-Host "Running threads=$t"

    $env:RAYON_NUM_THREADS=$t

    $result = cargo run --release --bin spend_prover_smoke

    $line = $result |
        Select-String "run=1"

    if ($line) {

        $text=$line.ToString()

        if ($text -match "prove_ms=([0-9.]+)") {
            $prove=$Matches[1]
        }

        if ($text -match "verify_ms=([0-9.]+)") {
            $verify=$Matches[1]
        }

        Add-Content $output "$t,$prove,$verify"

        Write-Host "$t,$prove,$verify"
    }
}