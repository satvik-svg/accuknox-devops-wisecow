#!/usr/bin/env bash
# Runs the same commands inside a wisecow pod before and after the KubeArmor
# policies are applied, and records what happened plus the KubeArmor alerts.
# Used by .github/workflows/kubearmor-proof.yaml, also works on any cluster
# where KubeArmor and wisecow are already installed.
set -uo pipefail

OUT=${OUT:-proof}
mkdir -p "$OUT"
NS=wisecow

# first running pod that is not on its way out
pod() {
  kubectl -n "$NS" get pod -l app=wisecow -o json \
    | jq -r '[.items[] | select(.metadata.deletionTimestamp == null and .status.phase == "Running")][0].metadata.name'
}

# name|command. Each one is run with kubectl exec inside the pod.
TRIES=(
  "list files with ls (not on the allowlist)|ls /"
  "start a different shell, sh (not on the allowlist)|sh -c id"
  "run apt-get (not on the allowlist)|apt-get --version"
  "read /etc/shadow|cat /etc/shadow"
  "run fortune (on the allowlist, should work)|/usr/games/fortune -s"
)

run_tries() {
  local phase=$1 p
  p=$(pod)
  echo "## $phase (pod $p)" | tee -a "$OUT/exec-results.md"
  echo "" >> "$OUT/exec-results.md"
  echo "| Attempt | Command | Exit code | Output |" >> "$OUT/exec-results.md"
  echo "|---|---|---|---|" >> "$OUT/exec-results.md"
  for t in "${TRIES[@]}"; do
    local name=${t%%|*} cmd=${t#*|} out rc
    # shellcheck disable=SC2086
    out=$(kubectl -n "$NS" exec "$p" -- $cmd 2>&1)
    rc=$?
    out=$(printf '%s' "$out" | head -c 300 | tr '\n|' '  ')
    echo "$phase: $name -> exit $rc: $out"
    echo "| $name | \`$cmd\` | $rc | ${out:0:160} |" >> "$OUT/exec-results.md"
  done
  echo "" >> "$OUT/exec-results.md"
}

check_app() {
  kubectl -n "$NS" port-forward svc/wisecow 4499:80 >/dev/null 2>&1 &
  local pf=$!
  sleep 3
  if curl -sf --retry 5 --retry-delay 1 --retry-all-errors http://127.0.0.1:4499/ | grep -q '<pre>'; then
    echo "App check $1: wisecow still serves cows" | tee -a "$OUT/exec-results.md"
  else
    echo "App check $1: wisecow did NOT answer" | tee -a "$OUT/exec-results.md"
    APP_BROKEN=1
  fi
  echo "" >> "$OUT/exec-results.md"
  kill $pf 2>/dev/null || true
}

: > "$OUT/exec-results.md"
APP_BROKEN=0

run_tries "Before policies"
check_app "before policies"

echo "Applying policies"
kubectl annotate ns "$NS" kubearmor-process-posture=block --overwrite
kubectl apply -f kubearmor/
kubectl -n "$NS" rollout restart deploy/wisecow
kubectl -n "$NS" rollout status deploy/wisecow --timeout=180s
sleep 10
kubectl get ksp -n "$NS" | tee "$OUT/policies.txt"
kubectl -n "$NS" get pods -o yaml | grep -i -E 'apparmor|kubearmor' | sort -u | tee "$OUT/pod-annotations.txt"

karmor logs -n "$NS" --json --logFilter=policy > "$OUT/karmor-logs.json" 2> "$OUT/karmor-logs.err" &
LOGS=$!
sleep 8

run_tries "After policies"
check_app "after policies"

sleep 10
kill $LOGS 2>/dev/null || true
wait $LOGS 2>/dev/null || true

# One line per alert, easier to read than the raw JSON
jq -r 'select(.PolicyName != null) | [.Action, .PolicyName, .ProcessName, .Resource, .Result] | @tsv' \
  "$OUT/karmor-logs.json" 2>/dev/null | sort | uniq -c > "$OUT/alerts-summary.txt" || true

BLOCKS=$(grep -c '"Action":"Block"' "$OUT/karmor-logs.json" || true)

{
  echo "# KubeArmor proof"
  echo ""
  echo '```'
  cat /tmp/probe.txt 2>/dev/null | head -40
  echo '```'
  echo ""
  cat "$OUT/exec-results.md"
  echo "## KubeArmor alerts (count, action, policy, process, resource, result)"
  echo ""
  echo '```'
  cat "$OUT/alerts-summary.txt"
  echo '```'
  echo ""
  echo "Block alerts seen: $BLOCKS"
} > "$OUT/summary.md"

cat "$OUT/summary.md"
[ -n "${GITHUB_STEP_SUMMARY:-}" ] && cat "$OUT/summary.md" >> "$GITHUB_STEP_SUMMARY"

if [ "$BLOCKS" -lt 1 ]; then
  echo "No Block alerts were recorded, so enforcement did not work"
  exit 1
fi
if [ "$APP_BROKEN" = 1 ]; then
  echo "The policies broke the app"
  exit 1
fi
