import { Plugin } from "@opencode/plugin"

/**
 * Advisor tool (Claude Code `/advisor`-style pattern).
 *
 * The executor model calls `advisor()` at decision points. The tool forwards
 * the current session transcript to a stronger, read-only model and returns a
 * short plan. The advisor cannot edit files, run commands, or call tools.
 *
 * Change MODEL below, or pass options via opencode.jsonc:
 *   "plugins": [{ "package": "./.opencode/plugins/advisor",
 *                 "options": { "model": { "providerID": "ollama-cloud",
 *                                         "id": "kimi-k3.1-pro" } } }]
 */

const MODEL = { providerID: "ollama-cloud", id: "deepseek-v4-pro:0813" }
const MAX_TRANSCRIPT_CHARS = 120_000

type AnyMessage = {
  role?: string
  content?: unknown
  parts?: unknown
  info?: { role?: string }
}

function stringify(value: unknown): string {
  if (typeof value === "string") return value
  if (value == null) return ""
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

function renderPart(part: unknown): string {
  if (typeof part === "string") return part
  if (!part || typeof part !== "object") return ""
  const p = part as Record<string, unknown>
  const type = String(p.type ?? "")

  if (type === "text") return String(p.text ?? "")
  // Thinking blocks are dropped: they are noise for the advisor.
  if (type === "reasoning" || type === "thinking") return ""

  if (type.includes("tool") && !type.includes("result")) {
    const name = p.name ?? p.tool ?? "tool"
    return `[tool ${String(name)}] ${stringify(p.input ?? p.args ?? {}).slice(0, 1500)}`
  }
  if (type.includes("tool") && type.includes("result")) {
    const output = p.output ?? p.result ?? p.content ?? ""
    return `[tool result] ${stringify(output).slice(0, 2500)}`
  }
  if (typeof p.text === "string") return p.text
  return ""
}

function renderMessage(message: AnyMessage): string {
  const role = message.role ?? message.info?.role ?? "unknown"
  const parts = Array.isArray(message.parts)
    ? message.parts
    : Array.isArray(message.content)
      ? message.content
      : null
  const body = parts
    ? parts.map(renderPart).filter(Boolean).join("\n")
    : typeof message.content === "string"
      ? message.content
      : stringify(message.content)
  if (!body.trim()) return ""
  return `[${role}]\n${body.trim()}`
}

function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text
  const head = Math.floor(limit * 0.25)
  const tail = limit - head
  return `${text.slice(0, head)}\n\n[... transcript truncated ...]\n\n${text.slice(-tail)}`
}

export default Plugin.define({
  id: "advisor",
  async setup(ctx) {
    const options = (ctx.options ?? {}) as {
      model?: { providerID: string; id: string }
      max_chars?: number
    }
    const model = options.model ?? MODEL
    const maxChars = Number(options.max_chars ?? MAX_TRANSCRIPT_CHARS)

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "advisor",
        description:
          "Consult a stronger, read-only advisor model with the full conversation. " +
          "Call this before committing to an approach, when stuck or when an error repeats, " +
          "and before declaring a complex task complete. The advisor returns a short plan, " +
          "key risks, and concrete next steps. It cannot edit files or run commands.",
        input: {
          type: "object",
          properties: {
            focus: {
              type: "string",
              description: "Optional specific question or decision to focus the advice on.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input: { focus?: string }, context: { sessionID: string }) => {
          try {
            const messages = (await ctx.session.context({
              sessionID: context.sessionID,
            })) as AnyMessage[]
            const transcript = truncate(
              messages.map(renderMessage).filter(Boolean).join("\n\n"),
              maxChars,
            )
            const focus = input?.focus?.trim()
            const prompt = [
              "You are a senior technical advisor reviewing an executor agent's work.",
              "You cannot edit files or run tools. Give guidance only.",
              "",
              "Return exactly these sections, briefly (under 500 words total):",
              "1. Recommended approach",
              "2. Key risks or wrong assumptions",
              "3. Next 2-3 concrete steps",
              "4. Completion check: is the work actually verified? (yes/no + what is missing)",
              "",
              focus
                ? `The executor asks specifically: ${focus}`
                : "The executor did not ask a specific question.",
              "",
              "Transcript of the executor's session so far:",
              transcript,
            ].join("\n")

            const { text } = await ctx.experimental.generate.text({ model, prompt })
            return {
              content: `ADVISOR (${model.providerID}/${model.id}):\n\n${text.trim()}`,
            }
          } catch (error) {
            const reason = error instanceof Error ? error.message : String(error)
            return { content: `Advisor unavailable: ${reason}` }
          }
        },
      })
    })
  },
})
