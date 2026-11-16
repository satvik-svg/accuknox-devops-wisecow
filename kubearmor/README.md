# KubeArmor policies for wisecow

Two policies, both selecting pods with `app: wisecow` in the `wisecow` namespace.

**wisecow-process-allowlist.yaml** (action `Allow`)
The pod may only run the programs `wisecow.sh` actually uses: bash, env, rm,
mkfifo, cat, sleep, nc, fortune, cowsay and perl (cowsay is a perl script).
With the namespace process posture set to `block`, every other program is
denied. So if someone gets a shell through the app, they cannot run `ls`,
`curl`, `apt`, `python` and so on.

**wisecow-block-sensitive.yaml** (action `Block`)
Extra rules that apply even to the allowed programs:
- no reading `/etc/shadow` or `/etc/gshadow`
- no writing anywhere under `/etc` or `/usr`
- no reading the service account token directory
- no raw sockets (stops tools like ping or packet crafting)

## Apply

```bash
# 1. Install KubeArmor (needs a node kernel with BPF-LSM or AppArmor)
curl -sfL http://get.kubearmor.io/ | sudo sh -s -- -b /usr/local/bin   # installs the karmor CLI
karmor install
karmor probe          # should show the enforcer as BPFLSM or AppArmor

# 2. Make anything not on the allowlist get blocked, not just logged
kubectl annotate ns wisecow kubearmor-process-posture=block --overwrite

# 3. Apply the policies and restart the pods so they pick them up
kubectl apply -f kubearmor/
kubectl -n wisecow rollout restart deploy/wisecow
```

## See the violations (for the screenshot)

Terminal 1, stream alerts:
```bash
karmor logs -n wisecow --logFilter=policy
```

Terminal 2, try things the policy should stop:
```bash
POD=$(kubectl -n wisecow get pod -l app=wisecow -o jsonpath='{.items[0].metadata.name}')
kubectl -n wisecow exec $POD -- ls /                    # not on the allowlist, should say Permission denied
kubectl -n wisecow exec $POD -- apt-get update          # blocked
kubectl -n wisecow exec $POD -- cat /var/run/secrets/kubernetes.io/serviceaccount/token   # blocked
kubectl -n wisecow exec $POD -- /usr/games/fortune      # allowed, still works
curl -k https://<your-host>/                            # app still serves cows
```

Terminal 1 should print alerts with `"Action":"Block"` and the policy name.
Take a screenshot showing the denied command and the matching alert side by
side, and put it in `kubearmor/screenshots/`.

## Note

Enforcement depends on the node. Managed clusters with Ubuntu or Bottlerocket
nodes (EKS, GKE, AKS) usually work. Kind running inside another container
may not let KubeArmor see container namespaces, in which case policies load
but nothing is enforced.
