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