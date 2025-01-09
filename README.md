# lonelypst

Tests and benchmarks the lonelypss / lonelypsc libraries

## Usage

The simplest tests starts up a broadcaster locally, configures
subscribers to connect to it, then verifies the subscriber has
the correct behavior

```bash
python -m lonelypst.tests.gencluster --db sqlite --s2b-auth hmac --b2s-auth hmac
```

Alternatively, can construct a test broadcaster setup on your
own and then run the same tests against that cluster:

```bash
python -m lonelypst.tests.tarcluster --ips 127.0.0.1:3003 127.0.0.1:3005 --auth ../subscriber-secrets.json
```

The more complicated setups require an AWS account and will setup
a specific configuration, primarily for benchmarking, and run
the same tests in the cloud. These are usually run one at a time
and will prompt to confirm the resources unless `--yes` is passed.

```bash
python -m lonelypst.tests.aws.small1
```
