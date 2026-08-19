# INSTALL — bootstrap this skill on a new machine

Everything below lets another agent (or a fresh opencode install) set up the
guard from scratch. The skill itself is the single source of truth: both
runtime files (patterns + plugin) and the test suite live inside
`~/.config/opencode/skills/global-agent-guardrails/`.

## Target layout (after install)

```
~/.config/opencode/skills/global-agent-guardrails/
├── SKILL.md                        # this skill's docs
├── INSTALL.md                      # this file
├── hooks/
│   └── dangerous-patterns.txt      # denylist (single source of truth)
├── plugin/
│   └── command-guard.ts            # plugin source (copy of what's installed)
└── test/
    └── test-guard.mjs              # test suite (port of upstream test-guard.sh)

~/.config/opencode/plugins/command-guard.ts   # INSTALLED plugin (auto-loaded)
```

## Step-by-step

1. **Create the skill directory and subdirectories:**

   ```bash
   mkdir -p ~/.config/opencode/skills/global-agent-guardrails/{hooks,plugin,test}
   ```

2. **Create `hooks/dangerous-patterns.txt`** — the denylist. One POSIX-ERE
   regex per line, `#` comments. Source: upstream repo
   `davidondrej/skills` → `hooks/dangerous-patterns.txt` (or copy from an
   already-installed machine).

3. **Create `~/.config/opencode/plugins/command-guard.ts`** — write the file
   below verbatim. This path matters: opencode auto-loads every `*.ts`/`*.js`
   in `~/.config/opencode/plugins/` (global) at startup — no `opencode.json`
   entry required. If the user keeps config under `$XDG_CONFIG_HOME`, the
   plugin resolves the patterns file via that env var automatically.

4. **Create `test/test-guard.mjs`** — the test suite. It exercises the SAME
   regex engine as the plugin (reads `dangerous-patterns.txt`, converts
   `[:space:]` → `\s`, multiline mode) against ~150 block/allow command cases.
   It never executes commands — pure string matching, safe to run. Source:
   upstream `hooks/test-guard.sh` ported from bash/grep to JS, or copy from an
   installed machine.

5. **Verify:**

   ```bash
   node ~/.config/opencode/skills/global-agent-guardrails/test/test-guard.mjs
   # must end with: passed: 149, failed: 0
   ```

6. **Restart opencode** (plugins load at startup), then e2e probe: ask the
   agent to run `git push --force` from a non-git directory — it must be
   blocked.

## Plugin source: ~/.config/opencode/plugins/command-guard.ts

```ts
import type { Plugin } from "@opencode-ai/plugin"
import { readFileSync, statSync } from "node:fs"
import path from "node:path"

const configDir =
  process.env.XDG_CONFIG_HOME || path.join(process.env.HOME ?? "", ".config")

const patternsFile = path.join(
  configDir,
  "opencode",
  "skills",
  "global-agent-guardrails",
  "hooks",
  "dangerous-patterns.txt",
)

let cache: { mtimeMs: number; patterns: RegExp[] } | null = null

function loadPatterns(): RegExp[] {
  const stat = statSync(patternsFile)
  if (cache && cache.mtimeMs === stat.mtimeMs) return cache.patterns

  const patterns = readFileSync(patternsFile, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"))
    .map((line) => new RegExp(line.replaceAll("[:space:]", "\\s"), "m"))

  cache = { mtimeMs: stat.mtimeMs, patterns }
  return patterns
}

export const CommandGuard: Plugin = async ({ client }) => {
  return {
    "tool.execute.before": async (input, output) => {
      if (input.tool !== "bash") return

      const command = output.args.command
      if (typeof command !== "string" || command.length === 0) return

      let patterns: RegExp[]
      try {
        patterns = loadPatterns()
      } catch (err) {
        await client.app.log({
          body: {
            service: "command-guard",
            level: "error",
            message: `failed to load patterns: ${String(err)}`,
          },
        })
        return
      }

      for (const pattern of patterns) {
        if (!pattern.test(command)) continue
        await client.app.log({
          body: {
            service: "command-guard",
            level: "warn",
            message: `blocked command matching ${pattern.source}`,
          },
        })
        throw new Error(
          "Command blocked by the global-agent-guardrails guard.\n" +
            `Matched pattern: ${pattern.source}\n\n` +
            `Command:\n${command}\n\n` +
            "Do not retry it or work around the guard; explain the block to the user instead.",
        )
      }
    },
  }
}

export default CommandGuard
```

## What the plugin does

- `tool.execute.before` fires before every tool call; only `bash` is checked.
- The command string lives at `output.args.command`; a `throw` blocks the tool
  (the model sees the error message and must not retry or work around it).
- Patterns are converted from POSIX ERE: `[:space:]` → `\s`, compiled with the
  `m` flag so `^`/`$` match each shell line like `grep -E`.
- The patterns file is re-read on mtime change — edits apply instantly, no
  restart needed.
- Fail-open: if the patterns file is missing or unreadable, the plugin logs an
  error via `client.app.log` and lets the command through. A broken config must
  never brick every bash call.

## Gotchas

- The denylist path in the plugin points into the skill directory — keep the
  skill folder name `global-agent-guardrails` unchanged, or edit the path.
- Keep `[:space:]` in patterns (never `\s`) — adapters convert it.
- Always run `test/test-guard.mjs` after editing patterns; add block + allow
  cases for every new pattern.
