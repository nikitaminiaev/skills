---
name: global-agent-guardrails
description: 'A denylist of catastrophic shell commands (rm -rf on / or ~, dd/mkfs, sudo rm, fork bombs, curl|sh, git push --force, gh repo delete) enforced by an opencode plugin hook (tool.execute.before) that blocks the bash tool before execution. Use when adding or tuning blocked-command patterns, testing the guard, debugging why a command was (or was not) blocked, or when the user mentions command guard, guardrails, dangerous command, or blocked bash command.'
---

# Global Agent Guardrails

A "bouncer" that blocks catastrophic shell commands before the `bash` tool runs them. The patterns file is the single source of truth; the opencode plugin (`command-guard.ts`) reads it on every bash call via the `tool.execute.before` hook and throws an Error to block execution.

It is a seatbelt against accidents, NOT a sandbox against a malicious agent (obfuscation like `python -c "shutil.rmtree(...)"` can slip past regex).

> **First-time setup / bootstrap on a new machine:** see `INSTALL.md` in this
> skill directory — it contains the full plugin source (`plugin/command-guard.ts`),
> where each file goes, and how to verify with the test suite.

## File map

```
~/.config/opencode/skills/global-agent-guardrails/
├── SKILL.md                        # this document
├── INSTALL.md                      # bootstrap guide + full plugin source (for new machines)
├── hooks/
│   └── dangerous-patterns.txt      # THE denylist: one POSIX-ERE regex per line, # comments
├── plugin/
│   └── command-guard.ts            # plugin source (template for installation)
└── test/
    └── test-guard.mjs              # test suite: run after ANY pattern change

~/.config/opencode/plugins/command-guard.ts   # installed plugin (auto-loaded, no config entry needed)
```

## How it works

1. opencode auto-loads `~/.config/opencode/plugins/command-guard.ts` at startup (no `opencode.json` entry needed).
2. Before every tool call, the `tool.execute.before` hook fires. If the tool is `bash`, the plugin:
   - reads `hooks/dangerous-patterns.txt` (mtime-cached, so pattern edits apply instantly, no restart),
   - converts POSIX `[:space:]` to `\s` and compiles each line as a JS regex in multiline mode (`m` flag, so `^`/`$` match each shell line like `grep -E`),
   - on a match, throws an Error → the command never runs, the model sees the block message.
3. Fail-open: if the patterns file is missing or a pattern fails to compile, the plugin logs the error via `client.app.log` and lets the command through — a broken config must never brick every bash call.

## State check (is it installed?)

```bash
ls ~/.config/opencode/plugins/command-guard.ts ~/.config/opencode/skills/global-agent-guardrails/hooks/dangerous-patterns.txt
node ~/.config/opencode/skills/global-agent-guardrails/test/test-guard.mjs   # must end "failed: 0"
```

If the plugin was just installed, restart opencode (plugins load at startup).

## Add or tune a pattern

1. Edit `hooks/dangerous-patterns.txt`. Write POSIX ERE (`grep -E`). Use `[[:space:]]`, never `\s` — the plugin converts `[:space:]` to `\s` automatically.
2. Add block + allow cases to `test/test-guard.mjs`, then run it. Must pass 100%.
3. Verify every pattern compiles in the JS engine:

```bash
node --input-type=module -e '
import { readFileSync } from "node:fs";
const f = process.env.HOME + "/.config/opencode/skills/global-agent-guardrails/hooks/dangerous-patterns.txt";
readFileSync(f, "utf8").split("\n").map(l => l.trim()).filter(l => l && !l.startsWith("#"))
  .forEach(l => new RegExp(l.replaceAll("[:space:]", "\\s"), "m"));
console.log("ok");'
```

Changes apply instantly — the plugin re-reads the file per bash call (mtime-cached).

## Design rule

Block only irreversible/catastrophic commands (data loss, disk wipe, repo deletion, token exfil). Local-destructive-but-recoverable commands (`git clean -fdx`, `rm -rf node_modules`, `rm -rf dist/`) stay ALLOWED — over-blocking kills agent usefulness.

Password managers are also a hard NO (pattern group 10): agents must never use their CLIs (`keepassxc-cli`, `rbw`, `nordpass` outright; `pass` with any argument at command position; `op` with its real subcommands — bare `op`/`pass` stay unblocked because they are common words), export gpg secret keys, or touch vault data. NOTE: `bw`, `bws`, `lpass` and `curl|wget | sh` are INTENTIONALLY allowed on this machine (owner's choice, see Gotchas).

## Gotchas (hard-won — do not rediscover)

- **Multiline mode is required.** The `m` flag makes `^`/`$` match each line like grep. Keep it in both the plugin and the tests.
- **`[:space:]` conversion is mandatory.** JS regexes have no POSIX classes; the plugin replaces `[:space:]` with `\s` (including inside compound classes like `[;&|[:space:]]` → `[;&|\s]` and negated classes like `[^;&|[:space:]"']` → `[^;&|\s"']`).
- **Fail-open is intentional.** Never make the hook throw on config errors, only on pattern matches.
- **False-positive class:** a harmless command whose ARGUMENT text contains a dangerous-looking string (e.g. passing a prompt mentioning `git push --force` on a CLI) gets blocked. Workaround: put the text in a file and reference it.
- **Over-blocking kills usefulness.** `rm -rf node_modules`, `git push --force-with-lease`, `git gc --prune=2.weeks.ago` are allowed on purpose.
- **Intentionally weakened on this machine (2026-08-17):** `curl|wget | sh` is NOT blocked (installers like nvm/rustup/docker rely on it — pattern commented out in the denylist), and `bw`/`bws`/`lpass` are NOT blocked (owner's choice; the `"*": "ask"` permission still guards real calls). Re-enable by uncommenting/restoring the lines in `dangerous-patterns.txt` and moving the matching test cases back to `block`.

## E2E verification recipe

Safe probe: ask the agent to run `git push --force` from a NON-git directory — blocked = guard works; "not a git repository" = guard failed but no harm done.

Direct engine test without any agent:

```bash
node --input-type=module -e '
import { readFileSync } from "node:fs";
const f = process.env.HOME + "/.config/opencode/skills/global-agent-guardrails/hooks/dangerous-patterns.txt";
const patterns = readFileSync(f, "utf8").split("\n").map(l => l.trim()).filter(l => l && !l.startsWith("#"))
  .map(l => new RegExp(l.replaceAll("[:space:]", "\\s"), "m"));
console.log(patterns.some(r => r.test("rm -rf /")) ? "BLOCKED (ok)" : "NOT BLOCKED (bad)");
console.log(patterns.some(r => r.test("rm -rf node_modules")) ? "BLOCKED (bad)" : "allowed (ok)");'
```
