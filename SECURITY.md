# Security

Kuroshio processes your portfolio and holdings data. Security reports are the
highest-priority issue class in this project — they outrank feature work and
everything else in the queue.

## Reporting a vulnerability

Report privately via [GitHub Security Advisories](../../security/advisories/new)
on this repo. Do not open a public issue for a suspected vulnerability.

I'll acknowledge reports within 72 hours. There is no bounty program.

## Scope

Today, the self-hosted engine runs entirely on your own machine with your own
API keys — there is no Kuroshio server receiving your data. Scope is the code
in this repo: providers, core, agents, and the CLI.

## Supported versions

Pre-release: the latest `main` is the only supported version, until the first
tagged release.
