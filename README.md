# nightshift

A read-only incident triage workflow. Give it an incident signal ID; it reads the signal, finds runbooks for that service, reads up to two, and returns a structured report with source IDs and a tool trace. It has a bounded plan, a strict tool allowlist, retries only on marked transient read failures, and stops rather than inventing evidence when a read fails.

Default mode uses a deterministic planner and synthetic incident data. The optional OpenAI planner makes a structured tool plan using `gpt-4o-mini`. Both modes run the **same** local read-only tools. The model does not get a shell or access to arbitrary files. No actual PagerDuty, monitoring service, deployment, or remediation API is connected. It's an orchestration sample, not an autonomous on-call engineer.

## Run

Python 3.10+, standard library only:

```sh
python3 -m unittest -v
python3 nightshift.py api-503
python3 nightshift.py queue-lag
```

The fixture lives in `sample_incidents.json`. You can provide a JSON dataset with `--data /path/to/file.json`; it needs `signals` and `runbooks` objects with the same shape. The dataset is read from an explicitly named local path, so do not point it at sensitive files or expose this CLI as a public endpoint without adding authentication and input controls. `--max-steps` accepts 2 to 5. The report has `summary`, `severity`, `evidence`, `next_steps`, `confidence`, `mode`, and `trace`. Evidence source IDs refer to keys in the supplied dataset. A runbook is advice to investigate, not a command executed by the program.

Optional LLM planner:

```sh
export OPENAI_API_KEY=... # set this privately, never commit it
python3 nightshift.py api-503 --mode openai
```

The model gets only signal metadata and must return JSON matching a schema. Its plan is validated again in code: it has to read the requested signal, find matching runbooks, then read at most two listed runbooks. Off-list tools, extra arguments, duplicate runbooks, out-of-order steps, and a runbook for another service are rejected. Calls have a 30-second HTTP timeout. There is no automatic retry of an LLM call, because repeating a paid call is not free. The OpenAI path is implemented but has not been exercised with a live key.

## Tests and limits

`python3 -m unittest -v` covers both fixtures, no matching runbook, missing signal, tool allowlist, plan order, duplicate steps, step budget, cross-service runbook rejection, transient retries/exhaustion, missing API key, unknown severity, and output shape. The OpenAI planner is mocked in tests. Real incidents need metrics freshness, runbook versioning, a stronger schema for all fields, per-service policy, and an operator review before any action. This sample takes no action. Its confidence label only says whether it found a matching runbook, not whether the suggested checks solve the incident.
