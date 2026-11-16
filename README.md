# Wisecow on Kubernetes

Wisecow is a tiny web server written in bash. Every request gets a random
fortune read out by an ASCII cow. This repo packages it as a container, runs
it on Kubernetes behind an HTTPS ingress, and ships it automatically with
GitHub Actions. It also has two small Python monitoring scripts and a
KubeArmor policy that locks the app down.

Original app: https://github.com/nyrahul/wisecow

> This repository is private. Read access has been given to the GitHub user
> **nyrahul** as the assignment asks.

## What is in here

| Path | What it does |
| --- | --- |
| `wisecow.sh` | The original app, unchanged. Listens on port 4499. |
| `Dockerfile` | Builds the image on `debian:bookworm-slim` with `fortune`, `cowsay` and OpenBSD `nc`. Runs as a non root user (uid 10001). |
| `k8s/base/` | Namespace, Deployment (2 replicas), ClusterIP Service and Ingress with TLS. |
| `k8s/overlays/prod/` | What CI deploys. Adds a Let's Encrypt `ClusterIssuer` so cert-manager gets a real certificate. |
| `k8s/overlays/local/` | For kind or minikube. Uses a self signed issuer and the host `wisecow.local`. |
| `.github/workflows/ci-cd.yaml` | Tests, builds and pushes the image, then deploys to the cluster. |
| `scripts/` | `system_health.py` and `app_health.py` with tests. |
| `kubearmor/` | Zero trust KubeArmor policies for the wisecow pods. |
| `hack/kind-config.yaml` | A kind cluster config for trying everything on a laptop. |

## Problem statement (from the original repo)

1. Create a Dockerfile and Kubernetes manifests to deploy wisecow. Expose it as a Kubernetes Service.
2. Add a GitHub Action that builds a new image when the repo changes.
3. Challenge: serve the app over TLS.

## 1. Run it locally with Docker

```bash
docker build -t wisecow:local .
docker run --rm -p 4499:4499 wisecow:local
# in another terminal
curl http://localhost:4499/
```

You should get a cow inside a `<pre>` block. Note that the script serves one
connection at a time and restarts `nc` after each reply, so firing many
requests back to back can get a "connection refused" for a split second.
That comes from the original script, not the container.

## 2. Deploy to Kubernetes

### Prerequisites on the cluster

- An ingress controller. The manifests use the `nginx` class:
  ```bash
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/cloud/deploy.yaml
  ```
- cert-manager:
  ```bash
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.1/cert-manager.yaml
  ```

### Production style (real domain, Let's Encrypt)

1. Point a DNS name at the ingress controller's external IP.
2. Replace `wisecow.example.com` in `k8s/base/ingress.yaml` with that name.
3. Set the image in `k8s/overlays/prod/kustomization.yaml` (CI does this for you).
4. Apply:
   ```bash
   kubectl apply -k k8s/overlays/prod
   kubectl -n wisecow get pods,svc,ingress,certificate
   ```
cert-manager answers the HTTP-01 challenge through the ingress, stores the
certificate in the `wisecow-tls` secret, and nginx starts serving HTTPS.
Plain HTTP is redirected to HTTPS.

### Local cluster (kind)

```bash
kind create cluster --config hack/kind-config.yaml
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/kind/deploy.yaml
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.1/cert-manager.yaml
kubectl -n cert-manager wait --for=condition=available deploy --all --timeout=180s

docker build -t wisecow:local .
kind load docker-image wisecow:local --name wisecow
kubectl apply -k k8s/overlays/local

kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 8443:443
# add "127.0.0.1 wisecow.local" to /etc/hosts, then
curl -k https://wisecow.local:8443/
```

The certificate is self signed, so `-k` (or a browser warning) is expected.

### Hardening in the Deployment

- Runs as uid 10001, `runAsNonRoot`, no privilege escalation, all Linux capabilities dropped.
- Read only root filesystem. `/app` (where the script makes its named pipe) and `/tmp` are small `emptyDir` volumes.
- No service account token mounted, since the app never calls the Kubernetes API.
- CPU and memory requests and limits, TCP readiness and liveness probes, rolling updates with zero downtime.

## 3. CI/CD with GitHub Actions

`.github/workflows/ci-cd.yaml` has three jobs:

1. **test**: renders both kustomize overlays and checks them with kubeconform, then runs the Python tests.
2. **build**: builds the image. On pull requests it only builds. On a push to `main` it pushes `USER/wisecow:sha-<commit>` and `USER/wisecow:latest` to Docker Hub, then runs a quick smoke test (`curl` must get a cow back).
3. **deploy**: only on pushes to `main`. Sets the new image tag with `kustomize edit set image`, runs `kubectl apply -k k8s/overlays/prod` and waits for the rollout. If the `KUBECONFIG` secret is missing it skips cleanly instead of failing.

### Secrets to add (Settings > Secrets and variables > Actions)

| Secret | Value |
| --- | --- |
| `DOCKERHUB_USERNAME` | Docker Hub username |
| `DOCKERHUB_TOKEN` | Docker Hub access token (Account settings > Personal access tokens, read and write) |
| `KUBECONFIG` | The kubeconfig for the target cluster, base64 encoded: `base64 -w0 ~/.kube/config` |

The kubeconfig must point at an API server GitHub's runners can reach (a
cloud cluster such as EKS, GKE, AKS, or a VM with a public IP). A kind
cluster on a laptop is not reachable from GitHub.

## 4. Monitoring scripts

```bash
cd scripts
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q tests
```

### system_health.py

Checks CPU, memory and disk usage and the number of running processes. Any
value over its limit is logged as `ALERT` on the console and in a log file.

```bash
python system_health.py                                   # one check, default limits of 80% and 500 processes
python system_health.py --cpu 70 --memory 75 --disk 90 --processes 400
python system_health.py --interval 30 --log-file /var/log/system_health.log   # keep running
```

Exit code is 1 when there is an alert, so it fits in cron or a CI step.

### app_health.py

Calls one or more URLs and prints `UP` or `DOWN` for each, based on the HTTP
status code (below 400 counts as up, or pass your own list with `--ok-codes`).
Timeouts and refused connections are `DOWN` too.

```bash
python app_health.py https://wisecow.example.com/
python app_health.py --insecure https://wisecow.local:8443/ http://localhost:4499/
python app_health.py --ok-codes 200,204 --interval 60 https://example.com/health
```

## 5. KubeArmor zero trust policy

See [kubearmor/README.md](kubearmor/README.md). In short, the pods may only
run the handful of programs `wisecow.sh` needs, and everything else is denied.

## Author

Satvik Srivastava (satvik764@gmail.com)
