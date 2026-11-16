#!/usr/bin/env bash
# Proves the KubeArmor policies in kubearmor/ really block things.
#
# It runs the same commands inside a wisecow pod before and after the policies
# are applied, then saves the results, the KubeArmor alerts and some debug
# details in $OUT (default ./proof). It fails if nothing was blocked, if `ls`
# still runs after the policies, or if the app stops serving cows.
#
# Expects kubectl access to a cluster that already runs KubeArmor and the
# wisecow Deployment in the wisecow namespace. Used by
# .github/workflows/kubearmor-proof.yaml.
set -uo pipefail

OUT=${OUT:-proof}
NS=wisecow
RESULTS="$OUT/exec-results.md"
mkdir -p "$OUT"

# "description|command". Each command is started from bash inside the pod,
# which is how a command injected through the app would run (bash is the
# app's own shell, so it is on the allowlist). The first program kubectl exec
# starts is not checked by AppArmor exec rules, because that is the moment the
# profile gets attached, so the tests never rely on it.
TRIES=(
  "list files with ls (not on the allowlist)|ls /"
  "start another shell, sh (not on the allowlist)|sh -c id"
  "run apt-get (not on the allowlist)|apt-get --version"
  "read /etc/shadow (blocked file)|cat /etc/shadow"
  "read /etc/hostname (allowed file)|cat /etc/hostname"
  "run fortune (on the allowlist)|/usr/games/fortune -s"
)

APP_BROKEN=0
AFTER_LS_RC="not run"

# Name of a running wisecow pod that is not shutting down. With "armored" the
# pod must also carry the AppArmor profile KubeArmor generated for it.
pod() {
  local filter='.metadata.deletionTimestamp == null and .status.phase == "Running"'
  if [ "${1:-}" = armored ]; then
    filter+=' and ([(.metadata.annotations // {})[] | tostring | select(test("kubearmor-"))] | length > 0)'
  fi
  kubectl -n "$NS" get pod -l app=wisecow -o json |
    jq -r "[.items[] | select($filter)][0].metadata.name // empty"
}

run_tries() {
  local phase=$1 mode=${2:-} p t name cmd out rc
  p=$(pod "$mode")
  {
    echo "## $phase (pod $p)"
    echo ""
    echo "| Attempt | Command | Exit code | Output |"
    echo "|---|---|---|---|"
  } >>"$RESULTS"
  for t in "${TRIES[@]}"; do
    name=${t%%|*}
    cmd=${t#*|}
    out=$(kubectl -n "$NS" exec "$p" -- bash -c "$cmd" 2>&1)
    rc=$?
    out=$(printf '%s' "$out" | head -c 160 | tr '\n|' '  ')
    echo "$phase: $name -> exit $rc: $out"
    echo "| $name | \`$cmd\` | $rc | $out |" >>"$RESULTS"
    if [ "$mode" = armored ] && [ "$cmd" = "ls /" ]; then AFTER_LS_RC=$rc; fi
  done
  echo "" >>"$RESULTS"
}

check_app() {
  local pf msg
  kubectl -n "$NS" port-forward svc/wisecow 4499:80 >/dev/null 2>&1 &
  pf=$!
  sleep 3
  if curl -sf --retry 5 --retry-delay 1 --retry-all-errors http://127.0.0.1:4499/ | grep -q '<pre>'; then
    msg="App check $1: wisecow still serves cows"
  else
    msg="App check $1: wisecow did NOT answer"
    APP_BROKEN=1
  fi
  echo "$msg"
  printf '%s\n\n' "$msg" >>"$RESULTS"
  kill "$pf" 2>/dev/null || true
}

: >"$RESULTS"
run_tries "Before policies"
check_app "before policies"

# Stream KubeArmor alerts for the namespace before anything changes
karmor logs -n "$NS" --json --logFilter=policy >"$OUT/karmor-logs.json" 2>"$OUT/karmor-logs.err" &
LOGS=$!
sleep 8

echo "Applying policies"
# Starting a program is a file action for KubeArmor, so the file posture
# decides what happens to programs that are not on the allowlist.
kubectl annotate ns "$NS" kubearmor-file-posture=block --overwrite
kubectl apply -f kubearmor/
kubectl -n "$NS" rollout restart deploy/wisecow
kubectl -n "$NS" rollout status deploy/wisecow --timeout=180s
# Wait for an armored pod and for the old pods to be gone
for _ in $(seq 1 30); do
  if [ -n "$(pod armored)" ] && [ "$(kubectl -n "$NS" get pod -l app=wisecow --no-headers | wc -l)" -le 2 ]; then
    break
  fi
  sleep 5
done
kubectl -n "$NS" get pods -o wide
kubectl -n "$NS" get ksp | tee "$OUT/policies.txt"
karmor probe >"$OUT/probe-after.txt" 2>&1 || true

run_tries "After policies" armored
check_app "after policies"

sleep 10
kill "$LOGS" 2>/dev/null || true
wait "$LOGS" 2>/dev/null || true

# Details that help when something goes wrong
{
  kubectl -n "$NS" get pods -o wide
  for p in $(kubectl -n "$NS" get pod -l app=wisecow -o name); do
    echo "== $p logs (previous run if it restarted)"
    kubectl -n "$NS" logs "$p" --previous --tail=30 2>/dev/null || kubectl -n "$NS" logs "$p" --tail=30
  done
  echo "== AppArmor profiles written by KubeArmor"
  for f in /etc/apparmor.d/kubearmor-wisecow-*; do
    echo "--- $f"
    sudo cat "$f"
  done
  echo "== AppArmor denials in the kernel log"
  sudo dmesg | grep 'apparmor="DENIED"' | grep kubearmor-wisecow | tail -40
} >"$OUT/debug.txt" 2>&1 || true

# One line per alert, easier to read than the raw JSON
jq -r 'select(.PolicyName != null) | [.Action, .PolicyName, .Operation, .Source, .Resource, .Result] | @tsv' \
  "$OUT/karmor-logs.json" 2>/dev/null | sort | uniq -c >"$OUT/alerts-summary.txt" || true
BLOCKS=$(grep -c '"Action":"Block"' "$OUT/karmor-logs.json" || true)

{
  echo "# KubeArmor proof"
  echo ""
  echo '```'
  sed -n '/Node 1/,$p' "$OUT/probe-after.txt" | head -40
  echo '```'
  echo ""
  cat "$RESULTS"
  echo "## KubeArmor alerts (count, action, policy, operation, source, resource, result)"
  echo ""
  echo '```'
  cat "$OUT/alerts-summary.txt"
  echo '```'
  echo ""
  echo "Block alerts seen: $BLOCKS"
} >"$OUT/summary.md"

cat "$OUT/summary.md"
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  cat "$OUT/summary.md" >>"$GITHUB_STEP_SUMMARY"
fi

status=0
if [ "$BLOCKS" -lt 1 ]; then
  echo "FAIL: no Block alerts were recorded"
  status=1
fi
if [ "$AFTER_LS_RC" = 0 ] || [ "$AFTER_LS_RC" = "not run" ]; then
  echo "FAIL: ls still ran after the policies, so the process allowlist is not enforced"
  status=1
fi
if [ "$APP_BROKEN" = 1 ]; then
  echo "FAIL: the policies broke the app"
  status=1
fi
exit "$status"
