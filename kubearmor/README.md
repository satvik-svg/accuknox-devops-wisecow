# KubeArmor policies for wisecow

Both policies select pods with `app: wisecow` in the `wisecow` namespace.

**`wisecow-process-allowlist.yaml`** (action `Allow`)
Only the programs `wisecow.sh` uses may run: bash, env, rm, mkfifo, cat,
sleep, nc, fortune, cowsay and perl (cowsay is a perl script). File reads are
allowed so the programs can load their libraries and data. With the namespace
file posture set to `block`, any other program is denied. KubeArmor treats
starting a program as a file action, which is why the file posture is the
setting that covers processes.

**`wisecow-block-sensitive.yaml`** (action `Block`)
Applies even to the allowed programs:
- no reading `/etc/shadow` or `/etc/gshadow`
- no writing under `/etc` or `/usr`
- no access to the service account token directory
- no raw sockets

## Apply

```bash
# KubeArmor needs a node kernel with BPF-LSM or AppArmor
curl -sfL http://get.kubearmor.io/ | sudo sh -s -- -b /usr/local/bin
karmor install
karmor probe

kubectl annotate ns wisecow kubearmor-file-posture=block --overwrite
kubectl apply -f kubearmor/
kubectl -n wisecow rollout restart deploy/wisecow
```

## See the violations

```bash
karmor logs -n wisecow --logFilter=policy          # terminal 1

POD=$(kubectl -n wisecow get pod -l app=wisecow -o jsonpath='{.items[0].metadata.name}')
kubectl -n wisecow exec "$POD" -- bash -c 'ls /'                 # Permission denied
kubectl -n wisecow exec "$POD" -- bash -c 'apt-get --version'    # Permission denied
kubectl -n wisecow exec "$POD" -- bash -c '/usr/games/fortune'   # allowed
```

`hack/kubearmor-proof.sh` does all of this and writes a report. The
`KubeArmor policy proof` workflow runs it on a GitHub hosted VM.

## Saved proof

`proof/` holds the output of a real workflow run
([run 43856148848](https://github.com/satvik-svg/accuknox-devops-wisecow/actions/runs/43856148848)),
and `screenshots/` has screenshots of that same run on GitHub:

| File | What it is |
| --- | --- |
| `screenshots/00-run-summary.png` | The green run and the KubeArmor probe output |
| `screenshots/01-blocked-commands.png` | Commands denied inside the pod after the policies |
| `screenshots/02-karmor-block-logs.png` | KubeArmor alerts with action `Block` |
| `summary.md` | Full report: KubeArmor probe, before and after results, alert counts |
| `exec-results.md` | Every command with its exit code and output |
| `karmor-logs.json` | Raw alerts from `karmor logs --json` |
| `apparmor-denials.log` | Kernel AppArmor denials for the wisecow profile |
| `apparmor-profile.txt` | AppArmor profile KubeArmor generated from the policies |

## Notes

- Enforcement depends on the node. Ubuntu nodes with AppArmor, such as the
  GitHub runners used here, work. Managed node images usually do too. kind nodes run inside
  Docker, so policies load but nothing is enforced there. That is why the
  proof uses k3s directly on the VM.
- In the alert for `cat /etc/shadow`, KubeArmor lists the shared library
  `cat` was loading as the resource. The `Source` field shows the real
  command.
