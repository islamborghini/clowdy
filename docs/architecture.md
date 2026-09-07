# Architecture

How Clowdy executes a function, why each piece is shaped the way it is, and
what the local topology maps to in AWS.

- [The request path](#the-request-path)
- [Control plane and data plane](#control-plane-and-data-plane)
- [Placement: how a worker is chosen](#placement-how-a-worker-is-chosen)
- [Warm containers and cold starts](#warm-containers-and-cold-starts)
- [Failure handling](#failure-handling)
- [Load balancing, at three layers](#load-balancing-at-three-layers)
- [Local topology to AWS](#local-topology-to-aws)
- [What is deliberately not built](#what-is-deliberately-not-built)

## The request path

```
   browser / curl
        |
        v
   nginx (frontend container)          serves the SPA, proxies /api
        |
        v
   nginx (infra/lb)                    least_conn across control-plane replicas
        |
   +----+----------------+
   |                     |
control-plane-1     control-plane-2    FastAPI: auth, CRUD, gateway routing
   |                     |
   |  Postgres           |             projects, functions, versions, invocations
   |  Redis              |             worker registry, in-flight counters
   |                     |
   +----+----------------+
        |
        v
   scheduler                           consistent hash + bounded load
        |
   +----+--------+--------+
   |             |        |
worker-1     worker-2  worker-3        FastAPI data plane, owns a Docker daemon
   |             |        |
   v             v        v
warm pool     warm pool  warm pool     containers kept alive between invocations
   |
   v
docker exec -> /app/runner.py -> handler(event, context)
```

Reading the code in that order:

| Step | File |
|---|---|
| HTTP entry, auth, routing | `backend/app/main.py`, `backend/app/routers/` |
| Resolve env vars, image, DATABASE_URL | `backend/app/services/context.py` |
| Choose a worker | `backend/app/services/scheduler.py` |
| Fleet membership and load | `backend/app/services/registry.py` |
| Dispatch and fail over | `backend/app/services/dispatcher.py` |
| Accept or refuse work | `backend/app/worker/main.py` |
| Warm pool | `backend/app/services/assignment_service.py` |
| Create containers | `backend/app/services/placement_service.py` |
| Run the code | `backend/app/services/worker_service.py` |

## Control plane and data plane

The split is the central design decision, and it is drawn where it is because
the two halves have opposite operational needs.

The **control plane** is ordinary stateless HTTP. It reads and writes Postgres,
verifies JWTs, matches gateway routes, and decides where work goes. Any replica
can serve any request. It scales on CPU, deploys with a rolling restart, and
loses nothing when a task is killed.

The **data plane** is a worker that owns a machine. It needs a Docker daemon, a
writable container runtime, and enough local disk for images. Its warm
container pool is per-node state that cannot be shared or moved. Killing a
worker mid-invocation kills a user's function.

Because the two differ this sharply, they get different infrastructure: the
control plane runs on Fargate, the workers run on EC2 instances in an auto
scaling group. That is the same split AWS makes for Lambda itself, where the
invoke front end is a managed service and the workers are EC2 hosts running
Firecracker.

The one thing that keeps this honest is that both halves are the same image and
the same codebase. A worker is `uvicorn app.worker.main:app`; a control plane is
`uvicorn app.main:app`. They cannot drift.

## Placement: how a worker is chosen

`backend/app/services/scheduler.py`

Round-robin is the obvious answer and it is the wrong one here.

Every worker keeps its own pool of warm containers, keyed by
`(image, network_enabled)`. Where a request lands therefore decides whether it
is a ~20ms exec into a running container or a ~700ms container creation.
Round-robin spreads consecutive calls to the same function across every worker
in the fleet, which converts one warm pool into N cold starts.

Hashing the pool key onto a fixed worker fixes affinity and creates a new
problem: one busy image pins all of its traffic to a single node while the rest
of the fleet idles.

So placement uses **consistent hashing with bounded loads**:

1. Hash `image|net=0` onto a ring of virtual nodes (64 per worker).
2. Walk the ring from that position.
3. Take the first worker carrying no more than `average * 1.25` in-flight
   invocations.
4. If every worker is above that bound, fall back to plain
   least-outstanding-requests.

Affinity when there is room, spillover when there is not. The balance factor is
the knob: lower spreads load more evenly and sacrifices warm hits, higher
preserves warm hits and tolerates hot spots.

The affinity key is deliberately the *image*, not the function ID. Warm
containers are reusable by any function sharing an image and network setting,
because user code is injected at exec time rather than baked into the
container. Hashing on the function ID would fragment the pool for no benefit.

Consistent hashing rather than `hash(key) % worker_count` matters for exactly
one reason: when a worker joins or leaves, modulo remaps nearly every key and
the whole fleet cold-starts at once. The ring only remaps the keys the departed
worker owned. `backend/tests/test_scheduler.py` asserts this.

## Warm containers and cold starts

`backend/app/services/assignment_service.py`

Containers run `sleep infinity` and stay alive between invocations. Code is
copied in with `put_archive` and run with `docker exec`, so one container serves
many invocations of many functions.

The pool is bounded three ways, because an unbounded pool is a memory leak with
extra steps:

- **Size**: at `max_pool_size`, releasing a container evicts the least recently
  used one.
- **Idle time**: a background reaper destroys containers idle longer than
  `idle_timeout` (default 5 minutes).
- **Health**: a container whose exec raised is destroyed rather than returned
  to the pool. Reusing a container in an unknown state is how one bad
  invocation poisons the next twenty.

Function timeouts are enforced *inside* the container with coreutils `timeout`,
not around the Docker API call. Docker's exec API has no timeout, and
abandoning the API call would leave the process running and the container
pinned forever.

## Failure handling

Failure detection is a TTL, and that is the whole mechanism.

Measured on the compose stack (3 workers, concurrency 4 each): killing a worker
mid-traffic caused zero failed requests -- in-flight dispatches failed over to
another node immediately -- and the dead worker left `/api/cluster` once its
heartbeat expired. Repeat invocations of one function stayed pinned to a single
worker at ~55ms warm against ~360ms cold.

Workers write a heartbeat key to Redis every ~5 seconds with a 15 second
expiry. Nothing deletes a dead worker: its key expires and it is gone from the
ring on the next read. No gossip protocol, no leader election, no consensus,
because the cost of one misplaced invocation is one retry.

Everything else is layered on top of that:

| Failure | What happens |
|---|---|
| Worker crashes | Key expires within 15s; scheduler stops selecting it |
| Worker is full | Returns 429; dispatcher tries the next worker in ring order |
| Worker unreachable | `httpx` error; dispatcher fails over, up to 3 workers |
| Whole fleet saturated | Scheduler returns no placement; API returns 503 with `Retry-After` |
| Every worker gone | Dispatcher falls back to executing in the control-plane process |
| Control-plane replica dies | nginx `max_fails` removes it; ALB health check does the same in AWS |
| Redis unavailable | Registry reports empty; the platform degrades to single-node |
| Function times out | `timeout` SIGKILLs it at 30s; logged with status `timeout` |
| Container is broken | Destroyed rather than pooled |

The two defaults worth stating out loud:

**Refuse rather than queue.** A saturated fleet returns 503 instead of
accepting work it cannot run. Queueing does not create capacity, it just moves
the queue somewhere less visible and makes latency unbounded.

**Admission control lives on the worker, not only in the scheduler.** The
control plane's view of a worker's load is up to one heartbeat stale, so the
worker enforces its own concurrency limit and refuses past it. Defense in
depth: the scheduler optimises placement, the worker guarantees the invariant.

## Load balancing, at three layers

Three different problems that are frequently treated as one:

**Layer 1 - client to control plane.** nginx `least_conn` (an ALB in AWS).
Control-plane requests are wildly uneven: listing projects is a 2ms database
read, invoking a function holds the connection for as long as the function
runs. Round-robin counts requests, so it keeps feeding a replica already
sitting on eight 20-second invocations. `least_conn` counts open connections,
which is what actually correlates with how busy a replica is.

**Layer 2 - control plane to worker.** The scheduler above. Not a load
balancer, because the placement decision depends on state (which node holds a
warm container for this image) that no load balancer can see. Workers register
themselves and are addressed directly. This is service discovery plus
application-aware placement, which is why there is no ALB in front of the
worker fleet in the Terraform.

**Layer 3 - worker to container.** The warm pool. Choosing which of several
identical containers runs the next invocation, which is load balancing over
execution slots.

## Local topology to AWS

`docker-compose.yml` and `infra/terraform/` describe the same system.

| docker-compose | AWS (`infra/terraform/`) | Why |
|---|---|---|
| `frontend` (nginx) | S3 + CloudFront, or ECS behind the ALB | Static assets do not need a server |
| `lb` (nginx `least_conn`) | Application Load Balancer | Same job, same health-check semantics |
| `control-plane` x2 | ECS Fargate service, autoscaled on CPU | Stateless, no host access needed |
| `worker` x3 | EC2 auto scaling group | Needs a Docker daemon; Fargate has none |
| `postgres` | RDS Postgres, storage autoscaling, 7-day backups | Not the interesting part of this project |
| `redis` | ElastiCache Redis, single node | Contents rebuild in one TTL; a replica is waste |
| image builds | ECR with lifecycle policies | Untagged images are the quiet cost centre |
| `.env` file | Secrets Manager, injected by the ECS agent | Task definitions are readable by anyone with `ecs:Describe*` |
| `migrate` one-shot service | `aws ecs run-task` with a command override | One task owns the schema, not N replicas |

Security decisions worth pointing at in the Terraform:

- Every security group rule references another security group, never a CIDR.
  The database is open to exactly the two things meant to reach it, and stays
  correct when the subnet layout changes.
- Only the ALB sits in a public subnet. Compute and data are private, with
  egress through a single NAT gateway.
- The worker instance profile has ECR pull and SSM only. Workers run untrusted
  user code, so their IAM role is the blast radius of a container escape. No
  S3, no database, no secrets.
- IMDSv2 is required on workers. Without it, a function that escaped its
  container could read instance credentials with one unauthenticated GET.
- The ALB health check hits `/api/health`, which touches no dependency.
  A health check that verifies the database turns one slow query into the ALB
  removing the entire fleet from service.

Cost is the reason there are two stacks. `infra/terraform/` is roughly
$110/month idle, most of it fixed cost for the ALB, NAT gateway, RDS, and
ElastiCache. `infra/terraform-single-node/` runs the identical compose topology
on one EC2 instance for about $15/month, or nothing at all on a free-tier
`t3.micro`. It still has two control-plane replicas, three workers, and a real
scheduler distributing between them. What it gives up is surviving the loss of
the machine.

## What is deliberately not built

Being explicit about the edges is more useful than pretending they are not
there.

**Workers share one Docker daemon under Compose.** Every worker container
mounts the host socket, so locally the fleet is three scheduler clients driving
one daemon. The distribution is real at the process level -- separate services,
separate warm pools, real HTTP dispatch, real failover -- but not at the kernel
level. In AWS each worker is its own EC2 instance with its own daemon, which is
what the topology is actually written for.

**Per-project dependency images are built on the control plane and are local to
it.** In the compose stack that works because the daemon is shared. In AWS it
would not: the build must push to ECR and workers must pull by tag. The build
step is the one component that would need to move to a dedicated task.

**Autoscaling uses CPU, not queue depth.** The better signal for the worker
fleet is the aggregate in-flight ratio, which the control plane already
computes for `/api/cluster`. Publishing that as a custom CloudWatch metric and
target-tracking on it is the natural next step; CPU is a proxy that lags.

**No per-tenant quotas.** Concurrency is capped per worker, so the fleet cannot
be overwhelmed, but one user can consume all of it. Real per-account
reservations need a token bucket per user in Redis at the dispatcher.

**Docker containers, not microVMs.** A container escape reaches the host.
Firecracker or gVisor is the real answer for running genuinely untrusted code;
this is a namespace boundary with resource limits, which is honest about being
a learning platform rather than a public one.

**Invocations are synchronous.** There is no queue, no async invoke, no
dead-letter destination. Adding SQS between the dispatcher and the fleet is the
obvious extension, and it is what would let the platform absorb bursts instead
of shedding them.
