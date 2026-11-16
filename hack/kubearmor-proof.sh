#!/usr/bin/env bash
# Runs the same commands inside a wisecow pod before and after the KubeArmor
# policies are applied, and records what happened plus the KubeArmor alerts.
# Used by .github/workflows/kubearmor-proof.yaml, also works on any cluster
# where KubeArmor and wisecow are already installed.
set -uo pipefail

OUT=${OUT:-proof}
mkdir -p "$OUT"
NS=wisecow

# First running pod that is not on its way out. With "armored" it also has
# to carry the AppArmor profile KubeArmor generated for it.
pod() {
  local filter='.metadata.deletionTimestamp == null and .status.phase == "Running"'
  if [ "${1:-}" = armored ]; then
    filter="$filter"' and ((.metadata.annotations // {}) | to_entries | map(select(.value | tostring | test("kubearmor-"))) | length > 0)'
  fi
  kubectl -n "$NS" get pod -l app=wisecow -o json \
    | jq -r "[.items[] | select($filter)][0].metadata.name // empty"
}

# name|command. Each command is run through bash inside the pod, the same way
# an attacker who found a command injection in the app would run it (bash is
# the app's own shell, so it is allowed). Note that the very first program
# kubectl exec starts is not checked by AppArmor exec rules, the profile is
# attached at that moment, so everything below is started from bash.
TRIES=(
  "list files with ls (not on the allowlist)|ls /"
  "start another shell, sh (not on the allowlist)|sh -c id"
  "run apt-get (not on the allowlist)|apt-get --version"
  "read /etc/shadow (blocked file)|cat /etc/shadow"
  "read /etc/hostname (allowed file)|cat /etc/hostname"
  "run fortune (on the allowlist, should work)|/usr/games/fortune -s"
)

run_tries() {
  local phase=$1 p
  p=$(pod "${2:-}")
  echo "## $phase (pod $p)" | tee -a "$OUT/exec-results.md"
  echo "" >> "$OUT/exec-results.md"
  echo "| Attempt | Command | Exit code | Output |" >> "$OUT/exec-results.md"
  echo "|---|---|---|---|" >> "$OUT/exec-results.md"
  for t in "${TRIES[@]}"; do
    local name=${t%%|*} cmd=${t#*|} out rc
    out=$(kubectl -n "$NS" exec "$p" -- bash -c "$cmd" 2>&1)
    rc=$?
    out=$(printf '%s' "$out" | head -c 300 | tr '\n|' '  ')
    echo "$phase: $name -> exit $rc: $out"
    if [ "${2:-}" = armored ] && [ "$cmd" = "ls /" ]; then AFTER_LS_RC=$rc; fi
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
AFTER_LS_RC=unset

run_tries "Before policies"
check_app "before policies"

# stream KubeArmor alerts for the wisecow namespace from here on
karmor logs -n "$NS" --json --logFilter=policy > "$OUT/karmor-logs.json" 2> "$OUT/karmor-logs.err" &
LOGS=$!
sleep 8

echo "Applying policies"
kubectl annotate ns "$NS" kubearmor-file-posture=block --overwrite
kubectl apply -f kubearmor/
kubectl -n "$NS" rollout restart deploy/wisecow
kubectl -n "$NS" rollout status deploy/wisecow --timeout=180s
# wait until a pod with the KubeArmor AppArmor profile is up, and the old ones are gone
for i in $(seq 1 30); do
  [ -n "$(pod armored)" ] && [ "$(kubectl -n "$NS" get pod -l app=wisecow --no-headers | wc -l)" -le 2 ] && break
  sleep 5
done
kubectl -n "$NS" get pods -o wide
kubectl get ksp -n "$NS" | tee "$OUT/policies.txt"
karmor probe > "$OUT/probe-after.txt" 2>&1 || true
kubectl -n "$NS" get pods -o yaml | grep -i -E 'apparmor|kubearmor' | sort -u | tee "$OUT/pod-annotations.txt"


run_tries "After policies" armored
check_app "after policies"

sleep 10
kill $LOGS 2>/dev/null || true
wait $LOGS 2>/dev/null || true


# Extra detail that helps when something goes wrong
{
  kubectl -n "$NS" get pods -o wide
  for p in $(kubectl -n "$NS" get pod -l app=wisecow -o name); do
    echo "== $p logs (previous run if it restarted)"
    kubectl -n "$NS" logs "$p" --previous --tail=30 2>/dev/null || kubectl -n "$NS" logs "$p" --tail=30
  done
  echo "== AppArmor profiles KubeArmor wrote"
  for f in /etc/apparmor.d/kubearmor-wisecow-*; do echo "--- $f"; sudo cat "$f"; done
  echo "== AppArmor denials in the kernel log"
  sudo dmesg | grep 'apparmor="DENIED"' | grep kubearmor-wisecow | tail -40
} > "$OUT/debug.txt" 2>&1 || true

# One line per alert, easier to read than the raw JSON
jq -r 'select(.PolicyName != null) | [.Action, .PolicyName, .ProcessName, .Resource, .Result] | @tsv' \
  "$OUT/karmor-logs.json" 2>/dev/null | sort | uniq -c > "$OUT/alerts-summary.txt" || true

BLOCKS=$(grep -c '"Action":"Block"' "$OUT/karmor-logs.json" || true)

{
  echo "# KubeArmor proof"
  echo ""
  echo '```'
  sed -n '/Node 1/,$p' "$OUT/probe-after.txt" 2>/dev/null | head -40
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
if [ "$AFTER_LS_RC" = 0 ] || [ "$AFTER_LS_RC" = unset ]; then
  echo "ls still ran after the policies, so the process allowlist is not enforced"
  exit 1
fi
if [ "$APP_BROKEN" = 1 ]; then
  echo "The policies broke the app"
  exit 1
fi
