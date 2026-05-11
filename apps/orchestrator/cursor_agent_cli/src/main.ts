import { Agent, CursorAgentError } from "@cursor/sdk";
import fs from "node:fs";
import process from "node:process";

type ChatMessage = {
  role: string;
  content?: string;
};

type RunnerInput = {
  mode: "prompt" | "rag";
  messages?: ChatMessage[];
  question?: string;
  systemPrompt?: string;
  mcpServerUrl?: string;
  model?: string;
  cwd?: string;
};

type RunnerOutput = {
  ok: boolean;
  status: "finished" | "error" | "cancelled" | "startup_error";
  result?: string;
  agentId?: string;
  runId?: string;
  durationMs?: number;
  model?: unknown;
  error?: string;
  retryable?: boolean;
  code?: string;
};

function readInput(): RunnerInput {
  const raw = fs.readFileSync(0, "utf-8").replace(/^\uFEFF/, "");
  const input = JSON.parse(raw) as RunnerInput;
  if (input.mode !== "prompt" && input.mode !== "rag") {
    throw new Error("Expected input.mode to be 'prompt' or 'rag'");
  }
  return input;
}

function messageContent(message: ChatMessage): string {
  return typeof message.content === "string" ? message.content : "";
}

function buildPrompt(input: RunnerInput): string {
  if (input.mode === "rag") {
    const question = (input.question || "").trim();
    const systemPrompt = (input.systemPrompt || "").trim();
    if (!question) {
      throw new Error("input.question is required for rag mode");
    }
    if (!input.mcpServerUrl?.trim()) {
      throw new Error("input.mcpServerUrl is required for rag mode");
    }
    return [
      "Работай как RAG-агент без изменения файлов, запуска команд и правок репозитория.",
      "Используй подключенные MCP tools `kb_search` и `kb_get_chunk` для поиска ответа в базе знаний.",
      "Если данных недостаточно, верни `status` равным `insufficient_context`.",
      "Финальный ответ должен быть строго валидным JSON без markdown, пояснений и code block.",
      "",
      "Системные правила RAG:",
      systemPrompt,
      "",
      "Вопрос пользователя:",
      question,
    ].join("\n");
  }

  const messages = input.messages || [];
  if (!Array.isArray(messages) || messages.length === 0) {
    throw new Error("input.messages is required for prompt mode");
  }

  const rendered = messages
    .map((message) => {
      const role = String(message.role || "user").toUpperCase();
      return `<${role}>\n${messageContent(message)}\n</${role}>`;
    })
    .join("\n\n");

  return [
    "Ты выполняешь один LLM-запрос для backend-сервиса.",
    "Не изменяй файлы, не запускай команды и не выполняй действия с репозиторием.",
    "Верни только финальный ответ assistant. Если в сообщениях запрошен JSON, верни строго JSON без markdown и пояснений.",
    "",
    rendered,
  ].join("\n");
}

function assistantTextFromEvent(event: unknown): string {
  if (
    typeof event !== "object" ||
    event === null ||
    !("type" in event) ||
    event.type !== "assistant" ||
    !("message" in event)
  ) {
    return "";
  }
  const message = event.message as { content?: unknown };
  if (!Array.isArray(message.content)) {
    return "";
  }
  let text = "";
  for (const block of message.content) {
    if (
      typeof block === "object" &&
      block !== null &&
      "type" in block &&
      block.type === "text" &&
      "text" in block
    ) {
      text += String(block.text);
    }
  }
  return text;
}

function requestIdFromEvent(event: unknown): string {
  if (typeof event !== "object" || event === null || !("request_id" in event)) {
    return "unknown";
  }
  return String(event.request_id);
}

function writeOutput(output: RunnerOutput): void {
  process.stdout.write(JSON.stringify(output));
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function main(): Promise<void> {
  const input = readInput();
  const apiKey = process.env.CURSOR_API_KEY?.trim();
  if (!apiKey) {
    throw new Error("CURSOR_API_KEY is required");
  }

  const mcpServerUrl = input.mcpServerUrl?.trim();
  const mcpServers = input.mode === "rag" && mcpServerUrl
    ? {
        knowledge_base: {
          type: "http" as const,
          url: mcpServerUrl,
        },
      }
    : undefined;

  const agent = await Agent.create({
    apiKey,
    model: { id: input.model?.trim() || process.env.CURSOR_MODEL?.trim() || "composer-2" },
    local: {
      cwd: input.cwd?.trim() || process.cwd(),
      settingSources: [],
    },
    mcpServers,
    name: input.mode === "rag" ? "airflow-rag-agent" : "airflow-prompt-runner",
  });

  let runId: string | undefined;
  try {
    const run = await agent.send(buildPrompt(input));
    runId = run.id;
    let streamedText = "";

    if (run.supports("stream")) {
      for await (const event of run.stream()) {
        streamedText += assistantTextFromEvent(event);
        if (
          typeof event === "object" &&
          event !== null &&
          "type" in event &&
          event.type === "request"
        ) {
          throw new Error(`Cursor Agent requested input or approval: ${requestIdFromEvent(event)}`);
        }
      }
    }

    const result = await run.wait();
    const text = (streamedText || result.result || "").trim();
    writeOutput({
      ok: result.status === "finished",
      status: result.status,
      result: text,
      agentId: agent.agentId,
      runId,
      durationMs: result.durationMs,
      model: result.model,
      error: result.status === "finished" ? undefined : `Cursor Agent run finished with status: ${result.status}`,
    });
  } finally {
    await agent[Symbol.asyncDispose]();
  }
}

main().catch((error: unknown) => {
  if (error instanceof CursorAgentError) {
    writeOutput({
      ok: false,
      status: "startup_error",
      error: error.message,
      retryable: error.isRetryable,
      code: error.code,
    });
    process.exit(1);
  }
  writeOutput({
    ok: false,
    status: "error",
    error: errorMessage(error),
  });
  process.exit(1);
});
